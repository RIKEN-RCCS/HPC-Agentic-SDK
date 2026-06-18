"""On-disk index of documentation chunks, with vector and keyword search.

The index directory contains:
  chunks.json     — list of {id, breadcrumb, url, text}
  embeddings.npy  — float32 matrix aligned with chunks.json (optional)

Vector search is used when both the embeddings file and the embedding
endpoint are available; otherwise queries fall back to BM25 keyword search,
so the docs server works without access to the serving infrastructure.
"""
import json
import math
import re
from collections import Counter
from pathlib import Path

import numpy as np

from rikyu_mcp.rag.embed import get_client


def chunk_text(chunk: dict) -> str:
    """The searchable text of a chunk — shared by the BM25 corpus and the
    embedding pipeline (ingest.py) so the two retrieval paths index the
    same representation."""
    return chunk["breadcrumb"] + "\n" + chunk["text"]


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


class _BM25:
    K1 = 1.5
    B = 0.75

    def __init__(self, documents: list[str]):
        doc_tokens = [_tokenize(d) for d in documents]
        self.doc_lens = [len(t) for t in doc_tokens]
        self.avg_len = sum(self.doc_lens) / max(len(self.doc_lens), 1)
        self.doc_freqs = [Counter(t) for t in doc_tokens]
        df = Counter()
        for tokens in doc_tokens:
            df.update(set(tokens))
        n = len(documents)
        self.idf = {term: math.log(1 + (n - f + 0.5) / (f + 0.5)) for term, f in df.items()}

    def score(self, query: str) -> list[float]:
        q_tokens = _tokenize(query)
        scores = []
        for freqs, length in zip(self.doc_freqs, self.doc_lens):
            s = 0.0
            for term in q_tokens:
                if term not in freqs:
                    continue
                tf = freqs[term]
                norm = tf * (self.K1 + 1) / (tf + self.K1 * (1 - self.B + self.B * length / self.avg_len))
                s += self.idf.get(term, 0.0) * norm
            scores.append(s)
        return scores


class DocsIndex:
    def __init__(self, index_dir: Path):
        self.index_dir = Path(index_dir)
        with open(self.index_dir / "chunks.json") as f:
            self.chunks: list[dict] = json.load(f)
        self._bm25 = _BM25([chunk_text(c) for c in self.chunks])
        self._embeddings = None
        emb_path = self.index_dir / "embeddings.npy"
        if emb_path.exists():
            matrix = np.load(emb_path).astype("float32")
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            self._embeddings = matrix / np.maximum(norms, 1e-12)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Return the top_k chunks with a 'score' and 'method' field added."""
        if self._embeddings is not None:
            try:
                return self._vector_search(query, top_k, get_client())
            except Exception:
                pass  # endpoint down — degrade to keyword search
        return self._keyword_search(query, top_k)

    def _vector_search(self, query: str, top_k: int, client) -> list[dict]:
        q = np.asarray(client.embed([query])[0], dtype="float32")
        q = q / max(float(np.linalg.norm(q)), 1e-12)
        scores = self._embeddings @ q
        order = np.argsort(-scores)[:top_k]
        return [
            {**self.chunks[i], "score": float(scores[i]), "method": "vector"}
            for i in order
        ]

    def _keyword_search(self, query: str, top_k: int) -> list[dict]:
        scores = self._bm25.score(query)
        order = sorted(range(len(scores)), key=lambda i: -scores[i])[:top_k]
        return [
            {**self.chunks[i], "score": scores[i], "method": "bm25"}
            for i in order
            if scores[i] > 0
        ]
