---
name: rikyu-reference
description: Use when answering any question about Rikyu supercomputer specifics — login, accounts, partitions, modules, storage, policies — or when unsure about a cluster detail. Search the official docs instead of guessing.
---

# Rikyu documentation reference

Rikyu is an early-access system and its documentation evolves. Do not answer
Rikyu-specific questions from memory — ground answers in the official docs.

## Workflow

1. `search_docs` (rikyu-docs server) with the user's question. Cite the
   returned source URLs in your answer.
2. If search results look incomplete, `list_doc_sections` shows everything
   the docs cover; `read_doc_section` reads a full section.
3. If the docs don't cover it, say so and check live state instead
   (`get_facility`, `get_resources`, or `run_command_on_cluster` with e.g.
   `module avail` on the rikyu-hpc server), or point the user to support:
   rccs-ai4s-support [at] ml.riken.jp.

## Known facts not (yet) in the docs

- Nodes are NVIDIA GB200: aarch64 Grace CPUs, 4 GPUs per node, 216 nodes.
- Partition QoS levels are gpu1/gpu2/gpu4/gpu8/gpu16; CPU share is 36 per GPU.
- Default wall time when `--time` is omitted: 12 hours.

## Keeping the index fresh

If docs seem outdated, rebuild the index: `python -m rikyu_mcp.rag.ingest`
(run from `server/`; add `--no-embed` if the embedding endpoint is unavailable).
