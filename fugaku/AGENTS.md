# AGENTS.md

Read [hpc-agent-core's `PORTING.md`](https://github.com/william-dawson/hpc-agent-core/blob/main/PORTING.md)
before changing this repository. Do not create a local `PORTING.md`.

## Non-negotiable design rules

1. Never modify `hpc-agent-core`; every Fugaku-specific behavior lives in
   `server/fugaku_mcp/`.
2. PJM (`pjsub`/`pjstat`/`pjdel`/`pjalter`) doesn't fit either of core's
   ready-made backends (Slurm, Grid Engine), so it's a local `PJMBackend`
   subclassing `hpc_agent_core.compute.base.SchedulerBackend` directly
   (`server/fugaku_mcp/compute.py`) — same approach IreneAgent's
   `BridgeBackend` and Miyabi-Agent's `PBSBackend` took for their own
   dialects. Do not try to force PJM through `SlurmBackend`/`GridEngineBackend`.
3. The MCP servers must start without network access or a config file.
   Report configuration errors only when a tool is actually called.
4. Default agent-created job scripts to `~/agent/jobs/`.
5. Show a command or job specification before executing/submitting it
   unless the user explicitly asks to run it directly.
6. Fugaku has no GPUs (A64FX CPU-only) — `PJMBackend` rejects
   `resources.gpus`/`gpu_cores_per_process` rather than silently ignoring
   them.
7. `pjsub` has no stdout/stderr path override flag at all (confirmed by the
   complete absence of a `-o`/`-e`/`--out`/`--err` entry across every
   official `pjsub` option table) — `PJMBackend` rejects
   `spec.stdout_path`/`stderr_path` rather than silently dropping them.
   Output always lands at `<name>.<job_id>.out`/`.err` in the submission
   directory.

## Confirmed Fugaku facts

Confirmed two ways during this port: RIKEN's official user-guide Sphinx
docs (job execution, MPI, layered-storage, access sections), and live
commands run directly against a real Fugaku login node (`id`, `pjstat
--help`, `pjacl --rg small`/`large`, storage layout via `df`/`ls`).

- Mandatory PJM submission fields: `-L "rscgrp=..."`, `-L "node=..."`,
  `-L "elapse=..."`, and `-g <groupname>`. The shared `fugaku` group every
  account belongs to is explicitly **denied** job submission — confirmed
  live via `pjacl --rg small`'s ACL dump ("pjsub allow own / + deny
  g(fugaku)"). Never hardcode a project group anywhere (code, guide, or
  `data/fugaku_config.json`) — resolve it via `config.default_group()`
  (`defaults.group` in `~/.hpc-agent/fugaku.json`, or `FUGAKU_GROUP`), and
  use an obviously-fake placeholder like `<your-project-group>` in
  examples. See Miyabi-Agent's git history for what goes wrong when a port
  hardcodes one contributor's own project instead.
- Second-layer storage volumes (`/vol0004`, etc.) must be declared via
  `#PJM -x PJM_LLIO_GFSCACHE=<volume>` whenever a job's work lives outside
  `$HOME` — also per-project, resolved via `config.default_gfscache_volume()`,
  never hardcoded.
- **`pjsub`'s "data area" check does not treat `$HOME` as a data area at
  all** — confirmed live the hard way, by a real submission from
  `~/agent/jobs/` failing with "The current directory is not a data area."
  A "data area" specifically means a group data volume
  (`/vol0n0m/data/<groupname>/`); home and everything under it are a
  *different* area type. `PJMBackend.submit()` therefore always passes
  `--no-check-directory`, matching RIKEN's own documented recommendation
  for home-directory submission (JobExecution/JobExecConsiderpoints). Don't
  remove that flag without re-deriving why it's there.
- The `trial` project group (the default "Startup Project" every new
  account gets) is restricted to `spot-*` resource groups only
  (`spot-small`/`spot-int`/`spot-large`/`spot-middle`) — `small`/`large`
  will be rejected under `trial` even though they work under a real
  research-project group.
- `pjsub --version`/`-h`/`pjstat --version` all fail ("PJM 0001/0201
  Unknown option") — confirmed live. There is no single scheduler-version
  probe command, unlike Slurm's `sinfo --version`; `doctor.py` checks that
  `pjsub`/`pjstat`/`pjdel`/`pjalter` are simply on `PATH` instead.
  `pjstat --rsc`/`pjshowrsc` returned only a header row with no occupancy
  data for every flag combination tried against this account — `get_resources`
  therefore returns their raw output rather than a fabricated parsed shape;
  re-verify this if a future account/deployment behaves differently.
- Resource groups `small` (1–384 nodes, ≤72h), `large` (385+ nodes, ≤24h),
  and `int` (interactive) are documented; the full current production list
  with exact per-project limits lives on the Fugaku website, not in any
  file bundled here — `pjacl --rg <name>` is the authoritative live source
  per account.

## Repository map

```
plugins/fugaku/                 plugin manifest, MCP wiring, and skills
server/fugaku_mcp/               local PJMBackend and MCP servers
server/fugaku_mcp/compute.py     PJMBackend: pjsub/pjstat/pjdel/pjalter
server/fugaku_mcp/data/          static facts and the hand-written Fugaku guide
server/tests/smoke.py            MCP smoke test; --job submits a real PJM job
```

## Validation status

Fully validated against a real Fugaku login node during this port (not a
paper port) — `fugaku-doctor` and all three `tests/smoke.py` tiers
(`--offline`, read-only, `--job`) were run for real:

- **doctor**: config file, SSH (`fn01sv0*`), all four PJM commands on
  `PATH`, guide bundled, docs index built — all passed. The shared RIKEN
  embedding endpoint returned 401 (no API key configured for this account,
  same as this user's other RIKEN-family plugins) — expected, falls back to
  BM25 cleanly, not a real failure.
- **offline tier**: both MCP servers register their full tool sets;
  `get_facility` returns real bundled data.
- **read-only tier**: `search_docs` (BM25) returns real guide content;
  `get_resources`, `get_job_statuses([])`, `run_command_on_cluster("id")`,
  and `fs_ls` all succeeded against the live cluster.
- **job tier**: a real one-node job (`small` resource group, project group
  `ra000009`) was submitted with `submit_job`, transitioned
  QUEUED → RUNNING → EXT, and its output at
  `~/agent/jobs/<name>.<job_id>.out` was read back via `fs_tail` and
  contained the expected compute-node hostname and `$PJM_JOBID` — job
  49866807, 2026-07-30.
- **A real bug was caught and fixed by this live job**: the first attempt
  failed with `pjsub`'s "The current directory is not a data area" error —
  `$HOME` (and everything under it, including `~/agent/jobs/`) turned out
  not to count as a PJM "data area" at all (that term specifically means a
  group data volume, `/vol0n0m/data/<groupname>/`). Fixed by always passing
  `--no-check-directory` in `PJMBackend.submit()`, matching RIKEN's own
  documented recommendation for home-directory submission — see "Confirmed
  Fugaku facts" above. `data/fugaku_guide.md` was also corrected; its first
  draft repeated the same wrong assumption.
- **Not exercised**: multi-node/MPI jobs, `spot-*` resource groups, the
  `large` resource group, interactive jobs (`pjsub --interact`, not exposed
  as a tool at all), `update_job`/`pjalter`, GPU rejection (trivially true —
  Fugaku has no GPUs, but the code path itself wasn't exercised against a
  live rejection), and the `defaults.gfscache_volume` config path (the test
  job stayed entirely under `$HOME`, so no `PJM_LLIO_GFSCACHE` declaration
  was needed).
