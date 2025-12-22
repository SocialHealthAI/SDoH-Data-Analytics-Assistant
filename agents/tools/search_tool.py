import os
import re
import logging
from typing import Any, Optional
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pydantic import PrivateAttr
from tavily import TavilyClient
from langchain.tools import BaseTool

# Make sure TavilyClient is importable in your runtime
# from your_tavily_module import TavilyClient

executor = ThreadPoolExecutor(max_workers=4)
SENTENCE_SPLIT_RE = re.compile(r"[.!?]\s+")
NORMALIZE_RE = re.compile(r"[^0-9a-z ]+")


class SearchTool(BaseTool):
    # model fields accepted by Pydantic / BaseTool constructor
    name: str = "search_tool"
    description: str = (
        "Use this tool to search the web for up-to-date information. "
        "Returns a single most-likely short fact string (for RAG ingestion)."
    )
    max_results: int = 5  # <- declare as a field so Pydantic accepts it

    # private runtime-only attribute (not a model field)
    _client: Any = PrivateAttr()

    def __init__(self, **kwargs: Any):
        # allow constructing with SearchTool(max_results=7) safely because it's declared above
        super().__init__(**kwargs)
        api_key = os.environ.get("TAVILY_API_KEY")
        # initialize your Tavily client here; replace with your real client class
        self._client = TavilyClient(api_key=api_key)

    def _extract_text_from_result(self, r: dict) -> str:
        for k in ("snippet", "excerpt", "summary"):
            if k in r and r[k]:
                return str(r[k])
        if r.get("title"):
            return str(r["title"])
        return str(r.get("url", ""))

    def _candidate_sentences(self, text: str) -> list[str]:
        parts = SENTENCE_SPLIT_RE.split(text)
        return [p.strip() for p in parts if 5 < len(p.strip()) <= 300]

    def _normalize(self, s: str) -> str:
        s_lower = s.lower()
        s_clean = NORMALIZE_RE.sub(" ", s_lower)
        s_clean = re.sub(r"\s+", " ", s_clean).strip()
        return s_clean

    def _run(self, query: str, run_manager: Optional[Any] = None) -> str:
        try:
            results = self._client.search(query=query, max_results=self.max_results)
        except Exception:
            logging.exception("Search client error")
            return ""

        candidates = []
        for r in results.get("results", [])[: self.max_results]:
            text = self._extract_text_from_result(r)
            if not text:
                continue
            candidates.extend(self._candidate_sentences(text))

        if not candidates:
            top = results.get("results", [])
            if top:
                t = top[0]
                title = t.get("title", "")
                url = t.get("url", "")
                return f"{title} — {url}".strip()
            return ""

        normalized_map = {}
        counts = Counter()
        for s in candidates:
            norm = self._normalize(s)
            if norm:
                counts[norm] += 1
                if norm not in normalized_map or len(s) > len(normalized_map[norm]):
                    normalized_map[norm] = s

        best_norm, _ = max(
            counts.items(), key=lambda kv: (kv[1], len(normalized_map.get(kv[0], "")))
        )

        best_sentence = normalized_map.get(best_norm, "").strip()
        if len(best_sentence) > 400:
            best_sentence = best_sentence[:400].rsplit(" ", 1)[0] + "..."

        return best_sentence

    async def _arun(self, query: str, run_manager: Optional[Any] = None) -> str:
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(executor, self._run, query, run_manager)
