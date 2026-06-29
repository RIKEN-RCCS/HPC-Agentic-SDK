"""Build the documentation index from the Rikyu docs source repository.

Chunks the English markdown by heading, attaches the published site URL with
the section anchor, and (when the embedding endpoint is configured) computes
embeddings. Run this whenever the docs change:

    python -m rikyu_mcp.rag.ingest                # clone fresh + embed if configured
    python -m rikyu_mcp.rag.ingest --source PATH  # use an existing checkout
    python -m rikyu_mcp.rag.ingest --no-embed     # keyword-search-only index
"""
import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

from rikyu_mcp import config

_HEADING = re.compile(r"^(#{1,4})\s+(.*)$")


def _slugify(title: str) -> str:
    """mkdocs-style anchor slug."""
    slug = title.strip().lower()
    slug = re.sub(r"[^\w\- ]", "", slug)
    return re.sub(r"\s+", "-", slug).strip("-")


def chunk_markdown(text: str, page_url: str) -> list[dict]:
    """Split a markdown page into one chunk per heading section.

    Each chunk carries a breadcrumb of its parent headings so retrieval and
    the model both see the context (e.g. 'Usage > Submit a batch job').
    """
    lines = text.splitlines()
    sections: list[dict] = []
    stack: list[tuple[int, str]] = []  # (level, title)
    current: list[str] = []
    in_code = False

    def flush():
        body = "\n".join(current).strip()
        if body and stack:
            title = stack[-1][1]
            sections.append({
                "breadcrumb": " > ".join(t for _, t in stack),
                "url": f"{page_url}#{_slugify(title)}",
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
    chunks: list[dict] = []
    for md_file in sorted((source / "docs" / "en").rglob("*.md")):
        text = md_file.read_text()
        chunks.extend(chunk_markdown(text, config.DOCS_SITE_BASE))
    for i, chunk in enumerate(chunks):
        chunk["id"] = i

    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "chunks.json", "w") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(chunks)} chunks to {out_dir / 'chunks.json'}")

    emb_path = out_dir / "embeddings.npy"
    if not embed:
        emb_path.unlink(missing_ok=True)
        print("Skipped embeddings (keyword search only).")
        return

    from rikyu_mcp.rag.embed import get_client
    client = get_client()

    import numpy as np

    from rikyu_mcp.rag.store import chunk_text
    vectors = client.embed([chunk_text(c) for c in chunks])
    np.save(emb_path, np.asarray(vectors, dtype="float32"))
    print(f"Wrote {len(vectors)} embeddings (dim {len(vectors[0])}) to {emb_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=None,
                        help="Existing checkout of the docs repo (otherwise cloned fresh).")
    parser.add_argument("--out", type=Path, default=config.DOCS_INDEX_DIR)
    parser.add_argument("--no-embed", action="store_true",
                        help="Skip embeddings; build a keyword-search-only index.")
    args = parser.parse_args()

    if args.source:
        build_index(args.source, args.out, embed=not args.no_embed)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                ["git", "clone", "--depth", "1", config.DOCS_REPO_URL, tmp],
                check=True,
            )
            build_index(Path(tmp), args.out, embed=not args.no_embed)


if __name__ == "__main__":
    main()
