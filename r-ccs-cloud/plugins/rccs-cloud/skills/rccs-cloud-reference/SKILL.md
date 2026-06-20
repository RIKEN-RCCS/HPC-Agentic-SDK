---
name: rccs-cloud-reference
description: Use when answering any question about R-CCS Cloud specifics — partitions, modules, hardware, storage, login procedure, GPU flags, OS differences — or when unsure about a cluster detail. Search the built-in guide instead of guessing.
---

# R-CCS Cloud documentation reference

The R-CCS Cloud is a heterogeneous research testbed. Do not answer
cluster-specific questions from memory — ground answers in the built-in guide,
and prefer live state for anything that changes over time.

## Workflow

1. `search_docs` (rccs-cloud-docs) with the user's question. Cite the
   returned source in your answer.
2. If results look incomplete, `list_doc_sections` shows the full table of
   contents; `read_doc_section` reads a section in full by its title.
3. For anything current or precise — node counts, installed software, queue
   limits, live occupancy — **check live state**, since the guide deliberately
   doesn't freeze these:
   - `get_facility` / `get_resources` (rccs-cloud-hpc) for partitions and node state.
   - `run_command_on_cluster` for `module avail` (software), disk usage (`df -h`).
4. If still uncovered, point the user to the R-CCS Cloud portal or support.

## Orientation (stable facts)

- **Heterogeneous cluster**: many partition families — CPU-only (fx700, genoa,
  r340), NVIDIA GPU (a100, b300, ai-*, qc-gh200, ng-dgx), AMD GPU (mi100,
  qc-mi250, fs-mi300*), Intel GPU (qc-pvc). Pick the partition for the hardware.
- **Modules are partition-specific**: each partition has a `system/<partition>`
  module that MUST be loaded first. Never use a system module from the wrong partition.
- **GPU flag**: most GPU partitions use `--gpus=<n>`; exceptions are qc-gh200
  and ng-dgx-m[0-3] (unified CPU+GPU superchips).
- **Architectures**: fx700 = A64FX (aarch64-like); qc-gh200, ng-dgx = NVIDIA
  Grace (aarch64); all others = x86_64. Cross-compile for fx700 using r340.
- **OS**: ng-dgx-m[0-3] = Ubuntu; all other partitions = Rocky Linux.
- **Login**: `login.cloud.r-ccs.riken.jp`; key-based SSH.
- **source /etc/profile** is required before any module commands in every batch script.

## Keeping the guide fresh

The docs index is built from `server/cloud_mcp/data/cloud_guide.md`. To revise
it, edit that file and rebuild:
`server/run.sh cloud_mcp.rag.ingest` (add `--no-embed` to skip vectors).
Search uses the shared RIKEN BGE-M3 endpoint when an API key is set and the
endpoint is reachable, and BM25 keyword matching otherwise.
