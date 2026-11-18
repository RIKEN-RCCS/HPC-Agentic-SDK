"""Client for the embedding model served by the user's LLM serving infrastructure.

Assumes an OpenAI-compatible `/v1/embeddings` endpoint (the shape exposed by
vLLM, text-embeddings-inference, llama.cpp server, etc.).

Extending this: a facility cannot edit this file. If your serving stack
speaks a different dialect, subclass EmbeddingClient in your own
facilities/<slug>/facility.py and override embed(), then pass an instance
of it to DocsIndex(index_dir, embed_client=...) (see rag/store.py) instead
of relying on get_client()'s default. Don't monkey-patch this module.
"""
import httpx

from hpc_agent_core import config
from hpc_agent_core.config import Facility


class EmbeddingClient:
    def __init__(self, base_url: str, model: str, api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    def embed(self, texts: list[str]) -> list[list[float]]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        response = httpx.post(
            f"{self.base_url}/embeddings",
            json={"model": self.model, "input": texts},
            headers=headers,
            timeout=httpx.Timeout(connect=3.0, read=30.0, write=10.0, pool=5.0),
        )
        response.raise_for_status()
        data = response.json()["data"]
        # The API may return items out of order; sort by index.
        data.sort(key=lambda item: item["index"])
        return [item["embedding"] for item in data]


def get_client(facility: "Facility | str") -> EmbeddingClient:
    """Build a client from `facility`'s registered configuration."""
    fac = config.resolve(facility)
    return EmbeddingClient(fac.embed_base_url, fac.embed_model, config.embed_api_key(fac))
