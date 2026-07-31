# AGENTS.md

Agent-facing notes for working in this repo. Read
[hpc-agent-core's `PORTING.md`](https://github.com/william-dawson/hpc-agent-core/blob/main/PORTING.md)
first — it's the general porting guide this repo was built from and isn't
duplicated here (no `PORTING.md` file lives in this repo). This file covers
what's specific to *this* port: design rules to keep honoring, RIKYU's
cluster facts, decisions made under uncertainty, and the repo map.

## Design rules (from hpc-agent-core's PORTING.md — do not violate)

1. **No write access to `hpc-agent-core`.** Every RIKYU-specific behavior
   lives in `server/rikyu_mcp/`, reached through `configure()` arguments,
   `SlurmBackend` constructor arguments, or — if nothing fits — a local
   equivalent that skips the `hpc_agent_core` module in question. If you
   think you need to edit the installed `hpc-agent-core` package, you've
   misunderstood something.
2. **Clarity over cleverness.** RIKYU is one of several machines built this
   way; a bit of RIKYU-specific duplication that reads clearly beats a
   generic abstraction that doesn't.
3. **The MCP server must never fail to start.** Nothing above module scope
   in `config.py`/`compute.py`/`hpc_server.py` touches the network or reads
   the config file eagerly. A missing/malformed config is a tool-call-time
   error ("run the configuring skill"), not a startup crash.
4. **Bias agent-created files into `~/agent/`.** `compute.py`'s
   `jobs_dir="agent/jobs"` already does this for job scripts; anything else
   this plugin creates on the cluster should follow the same bias unless
   the user gives an explicit path.
5. **Show before you run.** `submit_job` and `run_command_on_cluster`
   should be preceded by showing the user what's about to execute, unless
   they've explicitly said to just run it. This is enforced in the tools'
   docstrings (agent-facing instructions), not in code — there's no way to
   enforce "ask first" at the MCP protocol level.
6. **Never invent a documentation URL.** `docs_cite_url` is deliberately
   blank (see "Decisions made under uncertainty" below) — don't add one
   back into a skill or tool description.

## RIKYU cluster facts

Source: RIKYU's official user guide PDFs, originally fetched into `docs/`
(System Overview, Login, Slurm, Job Resources, Storage, Module Environment,
Spack, Welcome), read 2026-07-10. If RIKYU's documentation changes, re-read
the source and hand-edit `server/rikyu_mcp/data/rikyu_guide.md` and
`rikyu_config.json` — per PORTING.md §2, this repo deliberately never
auto-refetches a live site.

- **Scheduler**: Slurm, single partition `gpu`, documented at 400 nodes (the
  full GB200 NVL4 build), GPU vendor NVIDIA only. GPU request style is
  job-total (`--gpus=N`, never `--gres=gpu:N`); Slurm derives node count from
  the GPU count automatically (4 GPUs/node) — no job script example in the
  source docs ever sets `--nodes`. `--account` never appears in a job script
  either; treated as unused.
  `compute.py` uses `SlurmBackend(has_accounting=True, gpu_request_style="gpus_total")`
  — the plain first row of PORTING.md §6's table, and `hpc-agent-core`
  0.3.0's own `SlurmBackend` docstring names Rikyu explicitly as a verified
  `has_accounting=True` machine, so this wasn't a guess.
  - **`has_accounting=True` is now live-confirmed**, not just inferred:
    `sacctmgr -n -p show cluster format=Cluster` returns a registered
    cluster (`ai4s`), and `sacct -a -X --starttime now-3days ...` returns a
    clean header with zero data rows — accounting is configured and
    reachable; the empty result reflects a quiet queue window, not a
    disabled subsystem. (Verified via Eliott Jacopin's PR #4.)
  - **Live node count is currently lower than documented**: a live
    `sinfo` read on 2026-07-30 showed the `gpu` partition at 313 nodes, not
    400. Expected during RIKYU's Early-Access phase (through September
    2026) — not all nodes are in the controller's view yet. `get_resources`
    always reads live state, so this doesn't affect correctness; noted here
    so 313 doesn't look like a bug when you first see it. Revisit
    `rikyu_config.json`'s documented count once RIKYU is in full
    production. (Observed via Eliott Jacopin's PR #4 live verification.)
  - **`srun` cannot launch MPI ranks — use `mpirun` instead**, verified
    live 2026-07-31: `srun ./mpi_program` aborts in `MPI_Init` with an
    internal-runtime failure, despite `srun --mpi=list` listing `pmi2`/
    `pmix` plugins (root cause not further diagnosed — plugin availability
    alone doesn't mean the launch path works). `mpirun` (from `nvhpc-hpcx`
    or `nvhpc-hpcx-cuda13`) works correctly single- and multi-node,
    confirmed with a real 2-node/8-rank job — the only requirement is
    setting `resources.processes_per_node` to the rank count, or `mpirun`
    fails with "not enough slots" (Slurm otherwise only allocates 1 task
    slot). Documented in the submitting-jobs skill and `rikyu_guide.md`;
    the prior skill example used `srun`, which would have failed for any
    real MPI job.
- **GPU counts**: only 1, 2, 3, 4, 8, 12, 16 are accepted; `hpc_server.py`'s
  `submit_job` validates this before submission (`_validate_gpu_count`) so
  a bad count fails clearly instead of behaving unpredictably in Slurm.
- **Wall time**: flat 96-hour cap regardless of job size.
- **Storage**: home (`/home/USER`, 5 GB, Lustre, SSD-backed), group
  (`/data1/GROUP`, 1 TB, Lustre, HDD-backed), scratch (`/tmp`, 1.5 TB/GPU,
  xfs, node-local, wiped at job end).
- **Software**: Lmod modules for compiler/MPI toolchains (`nvhpc` and four
  variants); Spack (public instance at
  `/shared/software/spack-1.2.0/share/spack/setup-env.sh`) for applications.
- **Login**: `login.rikyu.r-ccs.riken.jp`; key registration via Open
  OnDemand's "SSH Public Key" app, not email-an-admin.

## Decisions made under uncertainty

This port was originally written without live SSH access to RIKYU — from
its official documentation only, per PORTING.md §1's instruction to prefer
a real login node smoke path when available, which wasn't available at the
time. Live access arrived later (see the accounting/node-count facts
above); what follows is what's still unresolved:

- **`docs_cite_url` was left blank deliberately**, not by default inertia.
  RIKYU's docs site (`docs.r-ccs.riken.jp/rikyu/en/`) is plausibly stable,
  but RIKYU itself is mid-Early-Access (through September 2026) and the
  site's long-term URL structure hasn't been observed to hold steady over
  time from here — PORTING.md §3's bar is "confident it'll still be there
  next month," which wasn't met. Revisit this once the machine (and its
  docs site) has been in production long enough to trust.
- **The Codex plugin manifest (`plugins/rikyu/.codex-plugin/plugin.json`,
  `.agents/plugins/marketplace.json`) mirrors the Claude Code manifest
  shape by analogy** — no authoritative Codex plugin schema was available
  to verify against while writing this. Check it against Codex's actual
  plugin docs before relying on Codex-side installation; the Claude Code
  manifests (`.claude-plugin/`) are the ones built from an established
  pattern and are more trustworthy as written.
- **`doctor` and `tests/smoke.py`'s read-only path are now live-verified**
  against real RIKYU SSH (`slurm` version reported, `get_resources`
  returning the live `gpu` partition, `run_command_on_cluster('hostname')`
  succeeding) — via Eliott Jacopin's PR #4. **The remaining PORTING.md §9
  gap is a real job submission**: `smoke.py --job` has still never been run
  (RIKYU compute is billed with no usage cap, so this is intentionally
  gated, not an oversight — see the README's `--job`/`--confirm-billing`
  section). That's the one piece of this port's completion criterion still
  outstanding.

## Repository map

```
.claude-plugin/marketplace.json         Claude Code marketplace manifest
.agents/plugins/marketplace.json        Codex marketplace manifest (see caveat above)
plugins/rikyu/
  .claude-plugin/plugin.json            Claude Code plugin manifest
  .codex-plugin/plugin.json             Codex plugin manifest
  .mcp.json                             launches rikyu-hpc-server / rikyu-docs-server
  skills/rikyu-{configuring,submitting-jobs,monitoring-jobs,reference,demo}/SKILL.md
server/
  pyproject.toml                        depends on hpc-agent-core>=0.3,<0.4
  rikyu_mcp/
    config.py                           configure() registration + load_cluster_config()
    compute.py                          SlurmBackend construction
    hpc_server.py                       the IRI-grouped MCP tool surface (see IRI_CHECKLIST.md)
    docs_server.py, doctor.py           thin wrappers over hpc_agent_core
    data/
      rikyu_config.json                 static machine facts (partitions, storage, modules, spack)
      rikyu_guide.md                    hand-written guide, chunked by rag/ingest.py
      docs_index/                       generated: chunks.json (+ embeddings.npy)
  tests/smoke.py                        read-only MCP stdio test; --job submits a real job
docs/                                    source PDFs (reference only, not shipped)
IRI_CHECKLIST.md                        endpoint-by-endpoint coverage
```
