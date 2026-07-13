---
name: rikyu-reference
description: Use when answering any question about Rikyu supercomputer specifics — login, accounts, partitions, modules, storage, policies — or when unsure about a cluster detail. Search the bundled guide instead of guessing.
---

# Rikyu documentation reference

Rikyu is an early-access system and its documentation evolves. Do not answer
Rikyu-specific questions from memory — ground answers in `search_docs`, which
searches a guide bundled with the agent (not the official site — see below).

## Workflow

1. `search_docs` (rikyu-docs server) with the user's question. Cite the
   section breadcrumb (e.g. "Running jobs"), not a URL — **do not tell the
   user to go visit the official docs site**; it isn't a reliable live
   reference at the moment, and nothing in this agent should send them there.
2. If search results look incomplete, `list_doc_sections` shows everything
   the guide covers; `read_doc_section` reads a full section.
3. If the guide doesn't cover it, say so and check live state instead
   (`get_facility`, `get_resources`, or `run_command_on_cluster` with e.g.
   `module avail` on the rikyu-hpc server), or point the user to support:
   rccs-ai4s-support [at] ml.riken.jp.

## Known facts not (yet) in the guide

- Nodes are NVIDIA GB200 NVL4: aarch64 Grace CPUs + B200 GPUs, 4 GPUs per
  node, 400 nodes.
- Single `gpu` partition; only 1, 2, 3, 4, 8, 12, or 16 GPUs are accepted per
  job (`--gpus=N`); CPU/memory share is 36 cores + ~400GB per GPU.
- Max wall time 96h regardless of GPU count.

## Keeping the index fresh

The guide (`server/rikyu_mcp/data/rikyu_guide.md`) is an original write-up
maintained by hand, not something re-scraped from a live site. If it goes
stale, edit the guide directly, then rebuild the index:
`python -m rikyu_mcp.ingest` (run from `server/`; it automatically falls
back to a BM25-only index when no embedding key is configured).
