---
name: hokusai-reference
description: Use when answering any question about HOKUSAI BigWaterfall2 (HBW2) specifics — login, accounts/projects, partitions, modules, storage, policies — or when unsure about a cluster detail. Search the built-in guide or check live state instead of guessing.
---

# HBW2 documentation reference

Do not answer HBW2-specific questions from memory — ground answers in the
built-in guide, and prefer live state for anything that changes over time.

## Workflow

1. `search_docs` (hokusai-docs server) with the user's question. Cite the
   returned source in your answer.
2. If results look incomplete, `list_doc_sections` shows the full table of
   contents; `read_doc_section` reads a section in full by its title.
3. For anything current or precise — node counts, installed software, queue
   limits, your core-time balance, disk usage — **check live state**, since the
   guide deliberately doesn't freeze these:
   - `get_facility` / `get_resources` (hokusai-hpc) for partitions and node state.
   - `run_command_on_cluster` for `module avail` (software), `listcpu -p <project>`
     (core-time), `lfs quota -p $UID $HOME` (disk usage).
4. If still uncovered, point the user to the HBW2 Portal
   (https://hokusai.riken.jp/hbw2/) or RIKEN R-CCS support
   (https://i.riken.jp/en/supercom/contact/) for accounts, allocations, policy.

## Orientation (stable facts)

- **CPU-first machine.** A large pool of standard-memory Intel x86_64 nodes plus a
  couple of very-large-memory nodes carry the bulk of the work; a small 4-node
  H100 GPU server is for occasional postprocessing. Think CPU/MPI first.
- **Partitions**: a default standard-memory partition (≈1 day wall time), a
  longer-walltime sibling (fewer nodes), a large-memory partition, and GPU
  partitions (interactive + batch). Default wall time is short if unspecified —
  read exact limits and live occupancy with `get_facility` / `get_resources`.
- **Projects**: every job needs a project ID (`RB…` RIKEN, `HP…`-derived HPCI);
  core-time is fair-share and finite. The agent holds a default and can read your
  balance.
- **Storage**: personal home (quota), per-project data area (opt-in, charged),
  shared scratch (auto-purged ~weekly), and per-job node-local disk. Lustre.
- **Login**: `hokusai.riken.jp` (round-robins to `hokusai1..4`); key-based SSH,
  keys registered on the HBW2 Portal.

## Keeping the guide fresh

The docs index is built from `data/hokusai_guide.md` (an original guide, not the
vendor manual). To revise it, edit that file and rebuild:
`server/run.sh hokusai_mcp.rag.ingest` (add `--no-embed` to skip vectors). Search
uses the shared RIKEN BGE-M3 endpoint when an API key is set and the endpoint is
reachable, and BM25 keyword matching otherwise.
