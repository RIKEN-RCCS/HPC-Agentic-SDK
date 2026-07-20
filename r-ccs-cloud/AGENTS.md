# RCCS-CloudAgent — agent instructions

Claude Code and Codex plugin for the RIKEN R-CCS Cloud: two MCP servers
(`rccs-cloud-hpc` for Slurm, `rccs-cloud-docs` for documentation search) plus
skills. See [README.md](README.md) for the user-facing overview.

This repo is a **thin machine-specific skin over
[`hpc-agent-core`](https://github.com/william-dawson/hpc-agent-core)** (a PyPI
package). The general porting process this repo follows — the mental model, the
rules, the machine-facts checklist, the config/compute wiring, validation, and
the standing invariants — is documented once, canonically, in
[hpc-agent-core's `PORTING.md`](https://github.com/william-dawson/hpc-agent-core/blob/main/PORTING.md)
(no copy or stub of it lives in this repo). Read it before changing how this
plugin wires into core. What follows here is only what is specific to *this*
machine.

## Design rules (read before changing code)

- **No write access to `hpc-agent-core`.** Every customization must be reachable
  from this repo: constructor arguments, subclassing, or writing an independent
  equivalent. If you think you need to edit core, re-read the relevant module's
  "Extending this" docstring — you've almost certainly misunderstood something.
- **Clarity over cleverness.** A little machine-specific redundancy that reads
  well beats a clever abstraction that doesn't.
- **The `rccs-cloud-hpc` tool surface mirrors the IRI Facility API.** Before
  adding, renaming, or removing a tool, update [IRI_CHECKLIST.md](IRI_CHECKLIST.md);
  new tools should map to an IRI endpoint (or be marked an explicit extension).
- **Tools are thin verbs; workflow knowledge lives in `plugins/rccs-cloud/skills/`.**
  A long docstring telling the model *when* to do something belongs in a SKILL.md.
- **All cluster interaction goes through `hpc_agent_core.middleware`** (login
  shell, `$HOME` cwd, base64-quote-proof payloads, 200 KB output cap). Never
  shell out to `ssh` from tool code.
- **Never write to stdout in server code** — the MCP stdio transport uses it for
  JSON-RPC. Log to stderr; middleware already redirects remotemanager's stdout.

### §10 invariants (must hold, no exceptions)

- **The MCP server never fails to start.** Missing/malformed config is a
  tool-call-time error pointing at the configuring skill, never a startup crash.
  Nothing at module scope in `config.py`/`compute.py`/`hpc_server.py` touches the
  network or reads the config file eagerly.
- **Bias agent-created files into one visible directory** — job scripts, staged
  uploads, and scratch default under `~/agent/` (the backend's default
  `jobs_dir="agent/jobs"` does this). Honor any explicit path the user gives.
- **Show before you run** — preview the JobSpec / command before `submit_job` or
  `run_command_on_cluster`, unless the user said to just run it.
- **Never invent a documentation URL** — `docs_cite_url` is blank (see below), so
  search results carry no "Source:" line; don't add one in a skill or docstring.

## Machine wiring (what's specific to the R-CCS Cloud)

- **Scheduler backend** (`server/cloud_mcp/compute.py`): `CloudSlurmBackend`, a
  subclass of `hpc_agent_core.compute.slurm.SlurmBackend` constructed with
  `has_accounting=True`, `gpu_request_style="gpus_total"`,
  `nodes_always_explicit=True`,
  `no_gpu_flag_prefixes=frozenset({"qc-gh200", "ng-dgx-m"})`. This is the exact
  combination core documents for RCCS-Cloud: the `--gpus=N` flag, but `--nodes`
  always explicit, and no GPU flag at all for the unified CPU+GPU superchips.
- **`source /etc/profile` injection**: the one thing core can't express. Every
  R-CCS Cloud batch script must `source /etc/profile` before any `module`
  command, and the batch shebang is a non-login shell, so nothing sources it
  automatically. `CloudSlurmBackend.render_script` overrides the base method to
  insert that single line right after the `#SBATCH` header (reusing the base
  `_header`/`render_body` helpers) — the canonical "override the one method that
  differs" pattern. Do not add `source /etc/profile` to a JobSpec's executable.

## Cluster facts (from live verification)

- SSH destination from config `ssh.host` (default alias `rccs-cloud`) →
  `login.cloud.r-ccs.riken.jp`. Key-based auth only.
- Scheduler is **Slurm** (verified: `slurm 24.05.8`), accounting **on** (`sacct`
  works). **sacct lags `sbatch` by ~1–2 s**, so a status query fired immediately
  after submit can transiently miss the job — this is documented in the
  monitoring skill and handled in `tests/smoke.py`.
- **No project/account ID required** — jobs without `--account` use the user's
  default Slurm account. `get_projects`/`get_project` query `sacctmgr` for
  informational purposes; there are no per-project allocation budgets to report.
- **GPU dialect**: `--gpus=<n>` job-total, `--nodes` always explicit; the
  superchip partitions `qc-gh200` and `ng-dgx-m[0-3]` take no GPU flag.
- Partitions span x86_64, aarch64 (fx700 A64FX; qc-gh200 / ng-dgx NVIDIA Grace),
  and NVIDIA/AMD/Intel GPUs; each has its own `system/<partition>` module.
  ng-dgx-m[0-3] runs Ubuntu, everything else Rocky Linux. Full table in
  `server/cloud_mcp/data/cloud_config.json` and the guide.
- Submitted scripts are kept under `~/agent/jobs/` on the cluster for auditability.
- **No PMI support** — `srun` cannot bootstrap MPI ranks on this cluster; jobs
  must launch MPI with `mpirun` (OpenMPI) instead. Since `mpirun` without PMI
  needs a manual hostfile/SSH setup for multi-node, jobs should default to
  single-node (`node_count: 1`). Found live, 2026-07-16, via a user hitting
  this while doing real research on the cluster — not from the guide.
  Documented in the submitting-jobs skill and `cloud_guide.md`.

### Live validation (2026-07-10)

Read-only smoke test passed (docs search, live `sinfo`, `hostname`, rsync
filesystem round-trip with sha256 verification). A real job (`207542`) submitted
to **qc-gh200** ran to completion: `source /etc/profile` made `module load
system/qc-gh200 nvhpc` succeed, no `--gpus` flag was emitted (superchip path),
the node reported `aarch64`, and the **GH200 GPU was visible** (`nvidia-smi -L`).
This exercised the full queue→run→complete→read-output path plus the
no-GPU-flag render path on real hardware.

## Decisions made under uncertainty

- **`docs_cite_url` left blank.** The guide is written in our own words and
  there's no public docs site we're confident is stable and worth citing, so
  search results carry no URL (per PORTING §3). If a stable site is confirmed
  later, set it in `config.py`, re-run `cloud_mcp.ingest`, and commit.
- **`config_dir_name=".rccs-cloud"`** is set so an earlier setup's
  `~/.rccs-cloud/config.json` keeps working; new configs use the common
  `~/.hpc-agent/rccs_cloud.json`.
- **Docs index committed BM25-only.** No embedding API key was available at build
  time, so `data/docs_index/` has `chunks.json` but no `embeddings.npy`. Search
  works via BM25; to add vectors, set an embedding key and re-run
  `python -m cloud_mcp.ingest`, then commit `embeddings.npy`.

## Documentation search (RAG)

The docs source is **`server/cloud_mcp/data/cloud_guide.md`** — an *original*,
plain-language guide (facts in our own words, so the index is freely
distributable). It omits generic HPC/Linux background and anything the agent can
read live (`sinfo`/`module avail`/disk usage). `hpc_agent_core.rag.ingest` chunks
it by heading into `data/docs_index/chunks.json`; rebuild via
`python -m cloud_mcp.ingest` after editing the guide, then commit the index.

The embedding endpoint (`http://llm.ai.r-ccs.riken.jp:11434/v1`) and model
(`bge-m3:567m`) are fixed constants registered in `config.py`; only the API key
is user-configurable. Do not make model/base_url user-configurable — the
committed vectors are tied to the model.

## Repository map

```
.claude-plugin/            Claude Code marketplace manifest
.agents/plugins/           Codex marketplace manifest
plugins/rccs-cloud/        plugin payload for both Claude Code and Codex
  .claude-plugin/          Claude Code plugin manifest
  .codex-plugin/           Codex plugin manifest
  .mcp.json                MCP launch config (uv tool run from the git remote)
  skills/                  rccs-cloud-{configuring,submitting-jobs,
                           monitoring-jobs,reference,demo}
IRI_CHECKLIST.md           API coverage tracker — keep in sync with hpc_server.py
server/
  pyproject.toml           depends on hpc-agent-core (pinned >=0.4,<0.5) + entry points
  run.sh                   local dev launcher for a cloud_mcp module
  cloud_mcp/
    config.py              configure() registration + load_cluster_config()
    compute.py             CloudSlurmBackend (source /etc/profile) + re-exports
    hpc_server.py          rccs-cloud-hpc MCP tools (IRI-grouped)
    docs_server.py         rccs-cloud-docs MCP tools (thin over core)
    doctor.py              health checks (thin over core)
    ingest.py              docs-index build entry point (thin over core)
    data/                  cloud_config.json, cloud_guide.md, docs_index/
  tests/smoke.py           live read-only + optional --job smoke test
docs/cloud_guide.md        the machine's official reference (source material)
```

Skill names are machine-prefixed so this plugin can be installed alongside the
other hpc-agent-core plugins without skill-name collisions.
