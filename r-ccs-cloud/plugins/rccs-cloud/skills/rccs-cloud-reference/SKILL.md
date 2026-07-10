---
name: rccs-cloud-reference
description: Use when answering any question about R-CCS Cloud specifics — partitions, modules, hardware, storage, login procedure, GPU flags, OS differences — or when unsure about a cluster detail. Search the built-in guide instead of guessing.
---

# R-CCS Cloud documentation reference

The R-CCS Cloud is a heterogeneous research testbed. Do not answer
cluster-specific questions from memory — ground answers in the built-in guide,
and prefer live state for anything that changes over time.

## Workflow

1. `search_docs` (rccs-cloud-docs) with the user's question. Cite the returned
   section in your answer. (Results carry no "Source:" URL — that's deliberate;
   don't invent one.)
2. If results look incomplete, `list_doc_sections` shows the full table of
   contents; `read_doc_section` reads a section in full by its breadcrumb.
3. For anything current or precise — node counts, installed software, queue
   limits, live occupancy — **check live state**, since the guide deliberately
   doesn't freeze these:
   - `get_facility` / `get_resources` (rccs-cloud-hpc) for partitions and node state.
   - `run_command_on_cluster` for `module avail` (software) or `df -h` (disk).
4. If still uncovered, point the user to the R-CCS Cloud portal or support.

## Orientation (stable facts)

- **Heterogeneous cluster**: many partition families — CPU-only (fx700, genoa,
  genoa-m, r340), NVIDIA GPU (a100, b300, ai-*, qc-a100, qc-h100, qc-gh200,
  ng-dgx), AMD GPU (mi100, qc-mi250, fs-mi300*), Intel GPU (qc-pvc). Pick the
  partition for the hardware.
- **Modules are partition-specific**: each partition has a `system/<partition>`
  module that MUST be loaded first. Never use a module from the wrong partition.
- **GPU flag**: most GPU partitions use `--gpus=<n>` (set `resources.gpus`);
  exceptions are qc-gh200 and ng-dgx-m[0-3] (unified CPU+GPU superchips, no flag).
- **Architectures**: fx700 = A64FX (aarch64); qc-gh200, ng-dgx = NVIDIA Grace
  (aarch64); all others = x86_64. Cross-compile for fx700 using r340.
- **OS**: ng-dgx-m[0-3] = Ubuntu; all other partitions = Rocky Linux.
- **Login**: `login.cloud.r-ccs.riken.jp`; key-based SSH.
- **`source /etc/profile`** is required before module commands in every batch
  script — the plugin emits it automatically.
- **Restrictions**: ai-h100l is team-restricted (use ai-h100l-pu, 30-min cap);
  qc-h100 is under repair; qc-mi210 GPUs are still being set up.

## Keeping the guide fresh

The docs index is built from `server/cloud_mcp/data/cloud_guide.md`. To revise
it, edit that file and rebuild:
`python -m cloud_mcp.ingest` (add `--no-embed` to skip vectors), then commit the
regenerated `data/docs_index/`. Search uses the shared RIKEN BGE-M3 endpoint
when an API key is set and reachable, and BM25 keyword matching otherwise.
