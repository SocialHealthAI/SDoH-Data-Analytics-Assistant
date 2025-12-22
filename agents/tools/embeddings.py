# CPU-safe embeddings using transformers (paste into Python)
from transformers import AutoTokenizer, AutoModel
import torch
import numpy as np
from langchain.embeddings.base import Embeddings
from typing import List
from sentence_transformers import SentenceTransformer

# tiny LangChain-compatible adapter
class SimpleSTEmbeddings(Embeddings):
    """
    LangChain SentenceTransformerWrapper does not support CPU device.  Create
    a compatible wrapper.
    """
    def __init__(self, model: SentenceTransformer):
        self.model = model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        # returns a list of vectors
        return [self.model.encode(t, convert_to_numpy=True).tolist() for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self.model.encode(text, convert_to_numpy=True).tolist()


class HF_CPU_Embeddings:
    """
    Provide a minimal, reliable embeddings implementation that:
    - Loads a small transformer model (e.g. "sentence-transformers/all-MiniLM-L6-v2")
    onto CPU only (no `.to("cuda")` or device-mapping calls).
    - Produces fixed-length dense vectors for documents and queries via
    mean-pooling of the model last_hidden_state, followed by L2 normalization.
    - Exposes two methods expected by typical LangChain/FAISS workflows:
        * embed_documents(texts: List[str]) -> List[List[float]]
        * embed_query(text: str) -> List[float]

    - Avoids the `SentenceTransformer(...)` wrapper which in some environments
      triggers a `meta tensor` or `.to()` error during initialization.
    - Suitable for producing query vectors at retrieval time and document vectors
      for indexing. For best nearest-neighbor results, use the same
      model when creating and querying the FAISS index.

    self.vectordb = FAISS.load_local(
        self.persist_dir,
        embeddings=emb,
        allow_dangerous_deserialization=True
    )
    """

    def __init__(self, model_name="sentence-transformers/all-MiniLM-L6-v2"):
        self.device = torch.device("cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)
        self.model = AutoModel.from_pretrained(model_name, trust_remote_code=False).to(self.device)
        self.model.eval()

    def _mean_pooling(self, model_output, attention_mask):
        token_embeddings = model_output[0]  # last_hidden_state
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        sum_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1)
        sum_mask = input_mask_expanded.sum(1)
        sum_mask = torch.clamp(sum_mask, min=1e-9)
        return sum_embeddings / sum_mask

    def embed_documents(self, texts):
        encoded = self.tokenizer(texts, padding=True, truncation=True, return_tensors="pt")
        for k in encoded:
            encoded[k] = encoded[k].to(self.device)
        with torch.no_grad():
            model_output = self.model(**encoded)
        pooled = self._mean_pooling(model_output, encoded["attention_mask"])
        arr = pooled.cpu().numpy()
        # L2 normalize
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        arr = arr / norms
        return arr.tolist()

    def embed_query(self, text):
        return self.embed_documents([text])[0]
