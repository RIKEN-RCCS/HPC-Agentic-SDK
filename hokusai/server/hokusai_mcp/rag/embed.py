"""Client for the embedding model served by the user's LLM serving infrastructure.

Assumes an OpenAI-compatible `/v1/embeddings` endpoint (the shape exposed by
vLLM, text-embeddings-inference, llama.cpp server, etc.). If your serving
stack speaks a different dialect, this is the only file to change.
"""
import httpx

from hokusai_mcp import config


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
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()["data"]
        # The API may return items out of order; sort by index.
        data.sort(key=lambda item: item["index"])
        return [item["embedding"] for item in data]


def get_client() -> EmbeddingClient:
    """Build a client from the configuration (shared RIKEN endpoint + model)."""
    return EmbeddingClient(config.EMBED_BASE_URL, config.EMBED_MODEL, config.embed_api_key())
