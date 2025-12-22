from pathlib import Path
from typing import Optional, Any, List, Iterable, Dict
from langchain.vectorstores import FAISS
from langchain.docstore.document import Document
from langchain.tools.retriever import create_retriever_tool
from langchain.prompts import PromptTemplate
import os

class DictionaryLocalTool:
    """
    Manages a FAISS vector DB used as a "dictionary" of schema chunks using embeddings
    from a local model.  Local embeddings can be a problem if a GPU is not defined.  The
    installs and devices must be constrained to CPU - torch, FAISS, SentenceTransfomers.
    - persist_dir: where the FAISS index + metadata are saved
    - model_name: model for SentenceTransformerWrapper embeddings
    - search_k: 'k' for retriever search
    - name/description/response_format are forwarded to create_retriever_tool
    """

    def __init__(self, persist_dir: str = "../../workspace/data", model_name: str = "all-MiniLM-L6-v2",
                 search_k: int = 6, name: str = "database_column_descriptions", description: str = "Query dictionary of database column descriptions to find tables and columns using natural language descriptions or concepts. Use this first when column names are unknown or described in natural language.",
                 response_format: str = "content_and_artifact"):
        self.persist_dir = str(Path(persist_dir))
        self.search_k = int(search_k)
        self.name = name
        self.description = description
        self.response_format = response_format
        self.model_name = model_name

        local_embeddings = os.environ.get("EMBEDDINGS")

        if local_embeddings == "local":
            from sentence_transformers import SentenceTransformer
            from embeddings import SimpleSTEmbeddings
            EMBEDDINGS_CLASS = lambda model_name: SimpleSTEmbeddings(
                SentenceTransformer(model_name, device="cpu")
            )
        else:
            from langchain.embeddings import OpenAIEmbeddings
            EMBEDDINGS_CLASS = lambda model_name=None: OpenAIEmbeddings()

        self.embeddings = EMBEDDINGS_CLASS(model_name)

        self.vectordb: Optional[FAISS] = None
        self.retriever = None
        self.tool = None

        self.doc_prompt = PromptTemplate.from_template(
            "Schema chunk metadata:\n"
            "table: {table}\n"
            "column: {column}\n"
            "text: {text}\n\n"
            "{page_content}"
        )

        # Only attempt to load *if* index files/folder are present.
        if self._index_exists():
            # don't swallow unexpected exceptions so user sees real errors
            self._load_index_if_exists()
        # else leave vectordb/tool as None (user must create_index)


    # -------------------------
    # Internal helpers
    # -------------------------
    def _index_exists(self) -> bool:
        p = Path(self.persist_dir)
        # FAISS saves e.g. index.faiss and index.pkl in the folder in many setups; check for folder presence
        return p.exists() and any(p.iterdir())

    def _load_index_if_exists(self):
        """Load persisted FAISS index (must exist). Raises on failure so caller sees the error."""
        # If you get here, caller already checked _index_exists()
        emb = self.embeddings
        # Let exceptions propagate — they indicate an actual problem (bad files, incompatible embeddings, etc.)
        self.vectordb = FAISS.load_local(
            self.persist_dir,
            embeddings=emb,
            allow_dangerous_deserialization=True,
        )
        self.retriever = self.vectordb.as_retriever(search_kwargs={"k": self.search_k})
        self.tool = create_retriever_tool(
            self.retriever,
            name=self.name,
            description=self.description,
            document_prompt=self.doc_prompt,
            response_format=self.response_format,
        )


    def _to_document(self, item) -> Document:
        if isinstance(item, str):
            page_content = item
            metadata = {"table": None, "column": None, "text": None}
        else:
            page_content = item.get("page_content") or item.get("content") or item.get("text") or ""
            metadata = dict(item.get("metadata") or {})
            for k in ("table", "column", "text"):
                if k in item and k not in metadata:
                    metadata[k] = item[k]
        return Document(page_content=page_content, metadata=metadata)


    def _dedupe_documents(self, docs: List[Document]) -> List[Document]:
        """
        Simple dedupe: remove docs with identical (table, column, text, page_content).
        You can replace with more sophisticated logic if desired.
        """
        seen = set()
        out = []
        for d in docs:
            key = (
                d.metadata.get("table"),
                d.metadata.get("column"),
                d.metadata.get("text"),
                d.page_content,
            )
            if key not in seen:
                seen.add(key)
                out.append(d)
        return out

    # -------------------------
    # Public API: index creation / management
    # -------------------------
    def create_index(
        self,
        full_mapping: dict,
        embeddings: Optional[Any] = None,
        persist_dir: Optional[str] = None,
        dedupe: bool = True,
        overwrite: bool = False,
    ):
        """
        Build & persist a FAISS index from a nested `full_mapping` dict:
           { table: {"table_description": "...", "columns": { col_name: col_desc, ... }}, ... }

        Each column becomes one text
        "Table: {table}, Column: {col}, Description: {desc}" and metadata stores
        {"table": table, "column": col, "text": text}.
        """
        if not isinstance(full_mapping, dict):
            raise TypeError("create_index expects a nested dict (full_mapping).")

        pd = str(Path(persist_dir)) if persist_dir else self.persist_dir
        emb = embeddings or self.embeddings

        texts: List[str] = []
        metadatas: List[Dict[str, Any]] = []
        seen_texts = set()

        for table, tinfo in full_mapping.items():
            cols = (tinfo.get("columns") if isinstance(tinfo, dict) else {}) or {}
            for col_name, col_desc in cols.items():
                col_desc_str = str(col_desc).strip() if col_desc is not None else ""
                text = f"Table: {table}, Column: {col_name}, Description: {col_desc_str}"
                if dedupe and text in seen_texts:
                    continue
                seen_texts.add(text)
                texts.append(text)
                metadatas.append({"table": table, "column": col_name, "text": text})

        if not texts:
            raise ValueError("No texts found in full_mapping to build the index.")

        ppath = Path(pd)
        ppath.mkdir(parents=True, exist_ok=True)  # ensure directory exists

        # If overwrite, remove only FAISS index files, leave directory itself
        if overwrite:
            for fname in ["index.faiss", "index.pkl"]:
                f = ppath / fname
                if f.exists():
                    try:
                        f.unlink()
                    except OSError as e:
                        print(f"Warning: could not remove {f}: {e!r}")

        # Build and save
        self.vectordb = FAISS.from_texts(texts=texts, embedding=emb, metadatas=metadatas)
        self.vectordb.save_local(pd)

        # create retriever & tool
        self.retriever = self.vectordb.as_retriever(search_kwargs={"k": self.search_k})
        self.tool = create_retriever_tool(
            self.retriever,
            name=self.name,
            description=self.description,
            document_prompt=self.doc_prompt,
            response_format=self.response_format,
        )

        self.persist_dir = pd
        return self.vectordb


    def rebuild_index(self, mapping: Iterable[Dict], **kwargs):
        """Convenience wrapper that forces overwrite=True when creating index."""
        return self.create_index(mapping, overwrite=True, **kwargs)

    def add_documents(self, mapping: Iterable[Dict], dedupe: bool = True):
        """
        Add documents to an existing index. If no index exists, raises.
        mapping: iterable of dicts convertible to Documents.
        """
        if self.vectordb is None:
            raise RuntimeError("No index loaded. Call create_index(...) first.")

        docs = [self._to_document(m) for m in mapping]
        if dedupe:
            docs = self._dedupe_documents(docs)

        # FAISS object supports add_documents
        self.vectordb.add_documents(docs)
        # persist updated index
        self.vectordb.save_local(self.persist_dir)

    def clear_index(self):
        """Remove persisted index files and reset in-memory state."""
        import shutil
        p = Path(self.persist_dir)
        if p.exists():
            shutil.rmtree(p)
        self.vectordb = None
        self.retriever = None
        self.tool = None

    # -------------------------
    # Tool accessors for agent
    # -------------------------
    def get_tool(self):
        """Return the single Tool instance to add to your agent tools list."""
        if not self.tool:
            raise RuntimeError("No tool available. Load or create an index first.")
        return self.tool

    def get_tools(self) -> List[Any]:
        """Return a list compatible with your other helper classes."""
        return [self.get_tool()]
