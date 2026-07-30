---
name: fugaku-reference
description: Answer Fugaku-specific questions from the bundled guide and live commands — resource groups, storage tiers, modules, compilers.
---

# Fugaku reference

Search the bundled guide first with `search_docs` (covers PJM basics,
resource groups, the layered-storage/LLIO gotcha, MPI job shape, module
system, and cross-compilation). For time-sensitive or account-specific
values, use live commands through `run_command_on_cluster`:

- `pjacl --rg <name>` — a resource group's real node/elapse limits for this
  account.
- `pjstat --limit` — live concurrent-job and node/core quotas.
- `module avail` / `module list` — currently installed/loaded software.
- `id` — this account's real project groups (never guess one).

Do not guess a resource-group limit, module version, or project group —
Fugaku's docs are explicit that the authoritative resource-group table
lives on the Fugaku website, not in any locally bundled file, and project
groups are account-specific.

Key facts worth remembering without a lookup: Fugaku has no GPUs (A64FX
CPU-only); every job needs `-g <groupname>`; `pjsub` has no stdout/stderr
path override; storage outside `$HOME` needs an explicit
`PJM_LLIO_GFSCACHE` declaration; compute-node binaries need cross-compiling
from the login node (or native building inside an interactive job).
