---
name: rccs-cloud-reference
description: Use to answer questions about R-CCS Cloud itself — hardware, partitions, storage, software, policies, or where to get help. Ground answers in the bundled guide and live tool output rather than prior knowledge.
---

# R-CCS Cloud reference

**Do not answer questions about this machine from memory.** Ground every
answer in the bundled guide or live tool output. The orientation facts at
the bottom of this skill are a fallback for when the tools are
unavailable — not the authoritative source.

## Workflow

1. `search_docs(facility="rccs-cloud", query=...)` on the `hpc-docs` server,
   with the user's question. Cite the section breadcrumb it returns (e.g.
   "Running jobs"), not a URL.
2. If results look incomplete,
   `list_doc_sections(facility="rccs-cloud")` shows the full table of
   contents and `read_doc_section(facility="rccs-cloud", breadcrumb=...)`
   reads one section in full.
3. **For anything that changes over time — queue occupancy, node counts,
   installed software versions, your project's balance — check live state
   instead**, since the guide deliberately doesn't freeze these:
   `get_facility(facility="rccs-cloud")` for static facts,
   `get_resources(facility="rccs-cloud")` for occupancy,
   `get_projects(facility="rccs-cloud")` for accounts, or
   `run_command_on_cluster(facility="rccs-cloud", command="module avail")`.
4. If the guide doesn't cover it and no tool answers it, say so plainly
   rather than guessing.

**Search results carry no "Source:" URL unless this facility registered
one, and most don't. That's deliberate — never invent a URL to send the
user to.**

## Facility-specific reference

The R-CCS Cloud is a **heterogeneous research testbed** — its point is
that partitions differ in hardware, OS, and toolchain. Almost every
question about it has a "which partition?" qualifier; ask for one if the
user hasn't given it.

### Orientation (stable facts — prefer live tools for anything current)

- **Partition families**: CPU-only (`fx700`, `genoa`, `genoa-m`, `r340`),
  NVIDIA GPU (`a100`, `b300`, `ai-*`, `qc-a100`, `qc-h100`, `qc-gh200`,
  `ng-dgx`), AMD GPU (`mi100`, `qc-mi250`, `fs-mi300*`), Intel GPU
  (`qc-pvc`). Pick the partition for the hardware you need.
- **Modules are partition-specific**: each partition has a
  `system/<partition>` module that must be loaded first. Never use a
  module from the wrong partition — it produces wrong-ABI segfaults, not a
  clean error.
- **GPU flag**: most GPU partitions use `--gpus=<n>` (set
  `resources.gpus`); the exceptions are `qc-gh200` and `ng-dgx-m[0-3]`
  (unified CPU+GPU superchips — no flag at all).
- **Architectures**: `fx700` is A64FX (aarch64); `qc-gh200` and `ng-dgx`
  are NVIDIA Grace (aarch64); everything else is x86_64. Cross-compile for
  fx700 on `r340`.
- **OS**: `ng-dgx-m[0-3]` runs Ubuntu; every other partition runs Rocky
  Linux. A wheel built for one may need rebuilding for the other.
- **Login**: `login.cloud.r-ccs.riken.jp`, key-based SSH.
- **`source /etc/profile`** must precede any module command in a batch
  script — the plugin emits it automatically, so don't add it yourself.
- **Known restrictions** (verify live, these change): `ai-h100l` is
  team-restricted — use `ai-h100l-pu`, which caps at 30 minutes;
  `qc-h100` has been under repair; `qc-mi210` GPUs were still being set up.
- **No project account is needed** — jobs without `--account` use the
  user's default Slurm account.

### Getting help

If neither the guide nor the tools answer it, point the user at the R-CCS
Cloud portal or its support contact.

## Keeping the guide fresh

The docs index is built from this facility's bundled guide
(`facilities/<dir>/data/`), an original hand-written write-up — never
re-scraped from a live site. If it goes stale, edit the guide and rebuild:
`python -m hpc_mcp.ingest rccs-cloud` (it falls back to a BM25-only index
when no embedding key is configured), then commit the regenerated
`docs_index/`.
