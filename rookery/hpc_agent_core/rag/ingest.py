"""Build a documentation index from a facility's bundled guide.

Per PORTING.md: this only ever chunks a local, hand-written guide file — it
never git-clones or fetches a remote docs site at ingest time. If a
facility's official docs are worth indexing directly, that's a deliberate,
occasional, human-reviewed re-sync (read the source, rewrite the guide in
your own words, re-run this, commit the diff), not something a script
re-fetches unattended.

    python -m hpc_agent_core.rag.ingest rikyu                # bundled guide + embeddings
    python -m hpc_agent_core.rag.ingest rikyu --source FILE  # use a specific markdown file
    python -m hpc_agent_core.rag.ingest rikyu --no-embed     # keyword-only index

Precondition: every facilities/*/facility.py must already be imported by
the time this runs (registering every facility), since defaults for
--source/--out/embedding settings come from the named facility's
registration. server/hpc_mcp provides the wrapper that does this.

Embeddings use the facility's registered endpoint (embed_base_url/
embed_model) and require an API key (<SLUG_UPPER>_EMBED_API_KEY or
embedding.api_key in that facility's config file, or the shared
RCCS_EMBED_API_KEY fallback). Without a key, ingest writes a BM25-only index
and says so.

End users never need to run this — chunks.json (+ embeddings.npy) is
committed to the repo under facilities/<slug>/data/docs_index/.
"""
import argparse
import json
import re
from pathlib import Path

from hpc_agent_core import config

_HEADING = re.compile(r"^(#{1,4})\s+(.*)$")


def chunk_markdown(text: str, page_url: str) -> list[dict]:
    """Split a markdown guide into one chunk per heading section.

    Each chunk carries a breadcrumb of its parent headings so retrieval and
    the model both see the context (e.g. 'Running jobs'). page_url is
    attached to every chunk verbatim — pass "" (the default from
    config.docs_cite_url(facility)) to cite nothing.
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


def build_index(facility: str, source: Path, out_dir: Path, embed: bool, page_url: str = "") -> None:
    fac = config.get_facility(facility)
    chunks = chunk_markdown(source.read_text(), page_url)
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
    if not (fac.embed_base_url and fac.embed_model):
        # Checked before embed_api_key(): a facility with no embedding
        # endpoint configured at all (embed_base_url="" at registration) can
        # still see embed_api_key() resolve truthy via the shared
        # RCCS_EMBED_API_KEY env fallback, which every facility's
        # embed_api_key() honors regardless of whether *that* facility has
        # an endpoint — checking the key alone would then try to embed
        # against a blank URL and crash with httpx.UnsupportedProtocol.
        emb_path.unlink(missing_ok=True)
        print(f"No embedding endpoint configured for {fac.slug!r} — wrote a "
              "BM25-only index (this is expected, not an error, for a "
              "facility with no shared embedding infrastructure).")
        return
    if not config.embed_api_key(fac):
        emb_path.unlink(missing_ok=True)
        print(f"No embedding API key configured for {fac.slug!r} — wrote a "
              f"BM25-only index (set {fac.env_prefix}_EMBED_API_KEY and re-run to add vectors).")
        return

    import numpy as np

    from hpc_agent_core.rag.embed import get_client
    from hpc_agent_core.rag.store import chunk_text
    vectors = get_client(fac).embed([chunk_text(c) for c in chunks])
    np.save(emb_path, np.asarray(vectors, dtype="float32"))
    print(f"Wrote {len(vectors)} embeddings (dim {len(vectors[0])}) to {emb_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("facility", help="Facility slug to build the docs index for, e.g. 'rikyu'.")
    parser.add_argument("--source", type=Path, default=None,
                        help="Markdown guide to index (defaults to the facility's bundled guide).")
    parser.add_argument("--out", type=Path, default=None,
                        help="Output directory (defaults to the facility's docs index dir).")
    parser.add_argument("--url", default=None,
                        help="URL to cite in results (defaults to the facility's docs_cite_url, usually blank).")
    parser.add_argument("--no-embed", action="store_true",
                        help="Skip embeddings; build a keyword-search-only index.")
    args = parser.parse_args()
    source = args.source or config.docs_source(args.facility)
    out = args.out or config.docs_index_dir(args.facility)
    url = args.url if args.url is not None else config.docs_cite_url(args.facility)
    build_index(args.facility, source, out, embed=not args.no_embed, page_url=url)


if __name__ == "__main__":
    main()
