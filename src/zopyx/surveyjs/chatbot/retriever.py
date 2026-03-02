"""Lightweight lexical retriever for chatbot document chunks."""

from __future__ import annotations

import math
import re
from collections import Counter

TOKEN_RE = re.compile(r"[a-zA-Z0-9_]{2,}")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text or "")]


class Retriever:
    def __init__(self, documents: list[dict]):
        self.documents = documents or []
        self.doc_freq = Counter()
        self._build_stats()

    def _build_stats(self) -> None:
        for doc in self.documents:
            content = doc.get("content", "")
            terms = set(tokenize(content))
            for term in terms:
                self.doc_freq[term] += 1

    def _idf(self, term: str) -> float:
        total = max(len(self.documents), 1)
        return math.log((total + 1) / (1 + self.doc_freq.get(term, 0))) + 1.0

    def score(self, query: str, doc: dict) -> float:
        q_terms = tokenize(query)
        if not q_terms:
            return 0.0
        d_terms = tokenize(doc.get("content", ""))
        if not d_terms:
            return 0.0

        d_count = Counter(d_terms)
        score = 0.0
        for term in q_terms:
            tf = d_count.get(term, 0)
            if tf <= 0:
                continue
            score += (1.0 + math.log(tf)) * self._idf(term)

        query_lower = (query or "").strip().lower()
        content_lower = (doc.get("content", "") or "").lower()
        if query_lower and query_lower in content_lower:
            score += 2.0

        norm = math.sqrt(len(d_terms))
        if norm > 0:
            score = score / norm
        return score

    def retrieve(self, query: str, top_k: int = 6) -> list[dict]:
        if not query:
            return []
        scored = []
        for doc in self.documents:
            value = self.score(query, doc)
            if value <= 0:
                continue
            scored.append((value, doc))
        scored.sort(key=lambda item: item[0], reverse=True)

        results = []
        for score, doc in scored[: max(top_k, 1)]:
            item = dict(doc)
            item["score"] = round(float(score), 6)
            results.append(item)
        return results
