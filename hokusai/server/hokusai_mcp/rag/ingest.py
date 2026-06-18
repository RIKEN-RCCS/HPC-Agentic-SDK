"""Build the documentation index from the HokusaiAgent guide.

The docs source is `data/hokusai_guide.md` — an original, plain-language guide to
HOKUSAI BigWaterfall2 written for users working through the agent. (It is *not* a
copy of the vendor User's Guide: facts only, in our own words, so the committed
index can be freely distributed.) This ingester chunks the markdown by heading
and writes data/docs_index/chunks.json (+ embeddings.npy).

    python -m hokusai_mcp.rag.ingest                  # bundled guide + embeddings
    python -m hokusai_mcp.rag.ingest --source FILE    # use a specific markdown file
    python -m hokusai_mcp.rag.ingest --no-embed       # keyword-only index

Embeddings use the shared RIKEN endpoint (config.EMBED_BASE_URL / EMBED_MODEL)
and require an API key (HOKUSAI_EMBED_API_KEY or embedding.api_key in the config
file). Without a key, ingest writes a BM25-only index and says so.

End users never need to run this — chunks.json (+ embeddings.npy) is committed.
"""
import argparse
import json
import re
from pathlib import Path

from hokusai_mcp import config

_HEADING = re.compile(r"^(#{1,4})\s+(.*)$")


def chunk_markdown(text: str, page_url: str) -> list[dict]:
    """Split a markdown guide into one chunk per heading section.

    Each chunk carries a breadcrumb of its parent headings so retrieval and the
    model both see the context (e.g. 'Choosing where a job runs').
    """
    lines = text.splitlines()
    sections: list[dict] = []
    stack: list[tuple[int, str]] = []  # (level, title)
    current: list[str] = []
    in_code = False

    def flush():
        body = "\n".join(current).strip()
        if body and stack:
            sections.append({
                "breadcrumb": " > ".join(t for _, t in stack),
                "url": page_url,
                "text": body,
            })
        current.clear()

    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            current.append(line)
            continue
        match = None if in_code else _HEADING.match(line)
        if match:
            flush()
            level = len(match.group(1))
            title = match.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
        else:
            current.append(line)
    flush()
    return sections


def build_index(source: Path, out_dir: Path, embed: bool) -> None:
    chunks = chunk_markdown(source.read_text(), config.DOCS_SITE_BASE)
    for i, chunk in enumerate(chunks):
        chunk["id"] = i

    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "chunks.json", "w") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(chunks)} chunks to {out_dir / 'chunks.json'}")

    emb_path = out_dir / "embeddings.npy"
    if not embed:
        emb_path.unlink(missing_ok=True)
        print("Skipped embeddings (BM25 keyword search only).")
        return
    if not config.embed_api_key():
        emb_path.unlink(missing_ok=True)
        print("No embedding API key configured — wrote a BM25-only index "
              "(set HOKUSAI_EMBED_API_KEY and re-run to add vectors).")
        return

    import numpy as np

    from hokusai_mcp.rag.embed import get_client
    from hokusai_mcp.rag.store import chunk_text
    vectors = get_client().embed([chunk_text(c) for c in chunks])
    np.save(emb_path, np.asarray(vectors, dtype="float32"))
    print(f"Wrote {len(vectors)} embeddings (dim {len(vectors[0])}) to {emb_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=config.DOCS_SOURCE,
                        help="Markdown guide to index (defaults to the bundled guide).")
    parser.add_argument("--out", type=Path, default=config.DOCS_INDEX_DIR)
    parser.add_argument("--no-embed", action="store_true",
                        help="Skip embeddings; build a keyword-search-only index.")
    args = parser.parse_args()
    build_index(args.source, args.out, embed=not args.no_embed)


if __name__ == "__main__":
    main()
