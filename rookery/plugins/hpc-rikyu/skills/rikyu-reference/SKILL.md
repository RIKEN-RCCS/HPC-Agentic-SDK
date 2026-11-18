---
name: rikyu-reference
description: Use to answer questions about RIKYU (RIKEN AI4S / GB200) itself — hardware, partitions, storage, software, policies, or where to get help. Ground answers in the bundled guide and live tool output rather than prior knowledge.
---

# RIKYU (RIKEN AI4S / GB200) reference

**Do not answer questions about this machine from memory.** Ground every
answer in the bundled guide or live tool output. The orientation facts at
the bottom of this skill are a fallback for when the tools are
unavailable — not the authoritative source.

## Workflow

1. `search_docs(facility="rikyu", query=...)` on the `hpc-docs` server,
   with the user's question. Cite the section breadcrumb it returns (e.g.
   "Running jobs"), not a URL.
2. If results look incomplete,
   `list_doc_sections(facility="rikyu")` shows the full table of
   contents and `read_doc_section(facility="rikyu", breadcrumb=...)`
   reads one section in full.
3. **For anything that changes over time — queue occupancy, node counts,
   installed software versions, your project's balance — check live state
   instead**, since the guide deliberately doesn't freeze these:
   `get_facility(facility="rikyu")` for static facts,
   `get_resources(facility="rikyu")` for occupancy,
   `get_projects(facility="rikyu")` for accounts, or
   `run_command_on_cluster(facility="rikyu", command="module avail")`.
4. If the guide doesn't cover it and no tool answers it, say so plainly
   rather than guessing.

**Search results carry no "Source:" URL unless this facility registered
one, and most don't. That's deliberate — never invent a URL to send the
user to.**

## Facility-specific reference

RIKYU is an **early-access system** and its documentation evolves. Its
official site is not a reliable live reference at the moment, so nothing in
this agent should send a user there — answer from the bundled guide and
live tools, or say the answer isn't available.

### Orientation facts (fallback only — prefer the tools)

- Nodes are **NVIDIA GB200 NVL4**: aarch64 Grace CPUs + B200 GPUs, 4 GPUs
  per node, ~400 nodes.
- A single `gpu` partition. Only **1, 2, 3, 4, 8, 12, or 16** GPUs are
  accepted per job (`--gpus=N`); the CPU/memory share follows at 36 cores
  and ~400 GB per GPU.
- Max wall time **96 h** regardless of GPU count.
- Storage: `/home/<user>`, group area `/data1/<group>`, and node-local
  `/tmp` (1.5 TB per requested GPU, wiped when the job ends).
- x86_64 binaries, containers, and Python wheels will not run — the whole
  machine is aarch64.

### Getting help

If neither the guide nor the tools answer it, point the user at RIKYU
support: `rccs-ai4s-support [at] ml.riken.jp`.

## Keeping the guide fresh

The docs index is built from this facility's bundled guide
(`facilities/<dir>/data/`), an original hand-written write-up — never
re-scraped from a live site. If it goes stale, edit the guide and rebuild:
`python -m hpc_mcp.ingest rikyu` (it falls back to a BM25-only index
when no embedding key is configured), then commit the regenerated
`docs_index/`.
