from typing import List, Union, Iterable, Optional
from sentence_transformers import SentenceTransformer
"""
CPU-safe adapter for SentenceTransformer that:
    - constructs the model on given device (default cpu),
    - exposes embed_documents / embed_query,
    - supports being called directly (emb(text) or emb([texts])) for compatibility.
"""

class SentenceTransformerWrapper:
    def __init__(self, model_name: str, device: str = "cpu"):
        # construct model explicitly on CPU (or requested device)
        self.model = SentenceTransformer(model_name, device=device)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        # returns nested Python lists (FAISS / LangChain expect that)
        embs = self.model.encode(list(texts), convert_to_numpy=True)
        return embs.tolist()

    def embed_query(self, text: str) -> List[float]:
        emb = self.model.encode([text], convert_to_numpy=True)[0]
        return emb.tolist()
    
    # Make the object callable for compatibility with code that does emb(x)
    def __call__(self, data: Union[str, Iterable[str]]) -> Union[List[float], List[List[float]]]:
        # if passed a single string -> treat as query
        if isinstance(data, str):
            return self.embed_query(data)
        # otherwise treat as iterable of strings -> documents
        return self.embed_documents(list(data))

