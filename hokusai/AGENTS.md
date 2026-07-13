# AGENTS.md — HOKUSAI BigWaterfall2 (HBW2) plugin

Agent-facing notes for working on *this* repo: the design rules it inherits,
the cluster facts specific to HBW2, decisions made under uncertainty, and a
map of where everything lives.

For the general porting process this repo follows, see
[hpc-agent-core's `PORTING.md`](https://github.com/william-dawson/hpc-agent-core/blob/main/PORTING.md).
Don't copy that guide here — read the canonical version.

## Design rules (from the porting guide)

1. **No write access to `hpc-agent-core`.** Every customization is reachable
   from this repo: `configure()` arguments, subclassing a backend, or writing
   our own equivalent. If it feels like core needs editing, re-read the
   relevant module's docstring — the extension point is already there.
2. **Clarity over cleverness.** A little machine-specific, readable code here
   beats a clever generic abstraction. HBW2 is deliberately close to core's
   defaults; the port is thin on purpose.
3. **The MCP server must never fail to start.** Missing/malformed config is a
   tool-call-time error, never a startup crash. Nothing above module scope in
   `config.py`/`compute.py`/`hpc_server.py` touches the network or reads the
   config file eagerly.
4. **Bias agent files into `~/agent/`.** Job scripts default to
   `~/agent/jobs/` (core's `jobs_dir` default). Honor any explicit path.
5. **Show before you run.** Before `submit_job`/`run_command_on_cluster`, show
   the user the spec/command and a one-line explanation unless told to just run.
6. **Never invent a docs URL.** `docs_cite_url` is blank (see below); search
   results carry no URL and nothing should add one.

## HBW2 cluster facts

- **Scheduler:** Slurm (23.02.6 observed live). **Accounting is ON** — `sacct`
  returns history and `sshare` reports fair-share; verified against the live
  login node.
- **GPU dialect:** job-total `--gpus=N` (`gpu_request_style="gpus_total"`),
  single vendor (NVIDIA H100 → `--nv`), and Slurm derives node count from the
  GPU count (`nodes_always_explicit=False`, core's default for gpus_total).
  This is row 1 of PORTING.md §6 exactly.
- **Partitions (live `sinfo`):** `mpc` (312 nodes, 24 h), `mpc_l` (156, 72 h),
  `lmc` (2, 24 h), `gpu` (3, 72 h), `gpu_i` (1, 24 h). Node counts and
  occupancy change — read them with `get_resources`, never hardcode.
- **Accounts:** `--account` mandatory; RIKEN `RB…`, HPCI `HP…`. Fair-share
  governs queue order and recovers gradually.
- **Storage:** `/home/<user>` (~4 TB), `/data/<projectID>` (opt-in, charged),
  `/tmp_work` (scratch, ~1-week purge), node-local disk (per-job, wiped).
  Lustre.
- **Software:** environment modules; Intel oneAPI primary (`intel` module →
  Intel compilers + Intel MPI; `intel/25.3.0`, `intelmpi/impi_25.3.0` live).
  Open MPI (`openmpi/4.1.6`) is an alternative that **conflicts** with Intel
  MPI. Launch with `srun`. Singularity for containers.
- **Login:** SSH key-only via `hokusai.riken.jp` (`hokusai1`–`hokusai4`); keys
  registered at `https://hokusai.riken.jp/hbw2/`.
- **Network:** compute nodes have no internet; proxy at
  `http://$SLURM_SUBMIT_HOST:3128`.
- **Connection quirks:** none — HBW2 works with core's shared
  `remotemanager.Computer` defaults, so no `computer_defaults` are passed.

## Decisions made under uncertainty

- **`has_accounting=True`** — the guide describes billing and fair-share but
  doesn't name a command. Confirmed live: `sacct` and `sshare` both work.
- **`docs_cite_url=""`** — the HBW2 portal (`hokusai.riken.jp/hbw2/`) is an
  auth-gated site, not a stable public docs page, so search results cite no
  URL (PORTING.md §3).
- **`get_projects` uses `sacctmgr` associations + `sshare`.** The guide gives
  no project-balance command; these are standard accounting-on Slurm queries
  and were verified to list the user's real accounts (`hp260089`, `rb230090`)
  with QOS and fair-share. Partition lists come back empty when associations
  aren't partition-pinned — that means "all allowed", not "none".
- **Default account lives in the user config (`defaults.account`) or
  `HOKUSAI_ACCOUNT`,** not in bundled facts — the project is a per-user
  choice. An older config layout used a top-level `"account"` key; the port
  does not read that (deliberately not carried forward).
- **The guide is used verbatim as the bundled `data/hokusai_guide.md`,** since
  `docs/hokusai_guide.md` was already written in the plain-language,
  live-defer-to-tools style §2 prescribes. `data/` is the shipped copy the
  docs index is built from; `docs/` is the human-facing source. Keep them in
  sync by hand if either changes.

## Validation status

Verified against the **real HBW2 login node** (not just doctor):
`get_facility`, `get_projects`, `get_resources`, and a full job lifecycle —
submitted job `8481063` on `mpc`, followed queued → active → completed, and
read its `slurm-*.out`. This is the PORTING.md §9 "submit a real job" bar.
The embedding endpoint was unreachable from the test network at the time,
so the docs index was initially BM25-only; rebuild with an embedding key on
the RIKEN network via `python -m hokusai_mcp.ingest`.

## Repo map

```
docs/hokusai_guide.md              the machine guide (human-facing source)
server/
  pyproject.toml                   package + console scripts, pins hpc-agent-core>=0.4,<0.5
  hokusai_mcp/
    config.py                      configure() registration + cluster-config/account helpers
    compute.py                     constructs the SlurmBackend (the one backend line)
    hpc_server.py                  the IRI-grouped MCP tool surface (jobs, resources, projects, fs_*)
    docs_server.py                 thin wrapper over hpc_agent_core.docs_server
    doctor.py                      thin wrapper over hpc_agent_core.doctor
    data/
      hokusai_config.json          static facts get_facility returns
      hokusai_guide.md             bundled guide (copy of docs/, what the index is built from)
      docs_index/                  generated: chunks.json (+ embeddings.npy with a key)
  tests/smoke.py                   read-only MCP stdio test; --job submits a real job
plugins/hokusai/
  .claude-plugin/plugin.json       Claude Code plugin manifest
  .codex-plugin/plugin.json        Codex plugin manifest
  .mcp.json                        launches hokusai-hpc + hokusai-docs
  skills/                          configuring, submitting-jobs, monitoring-jobs, reference, demo
.claude-plugin/marketplace.json    Claude Code marketplace manifest
.agents/plugins/marketplace.json   Codex marketplace manifest
README.md / AGENTS.md / IRI_CHECKLIST.md
```
