---
name: benchkit
description: Guide for using and contributing to BenchKit (RIKEN-RCCS), a shell-first benchmarking framework that builds/runs HPC applications across multiple systems, collects results, and reports them to a portal. Use when adding a benchmark application to BenchKit, registering a new target system/site, running or testing a BenchKit benchmark locally, or understanding a `programs/<code>/{build.sh,run.sh,list.csv}` layout.
user-invocable: true
---

# BenchKit — building and running HPC benchmarks across systems

BenchKit (from RIKEN-RCCS) is a **shell-first** benchmarking framework: for
any given application, a `build.sh` and `run.sh` any HPC user could read and
run by hand define how it's built and executed on each target system, and a
`list.csv` defines which (system, node-count, rank, thread) combinations to
run. There is no heavy framework abstraction layer between you and the actual
build/run commands — that's a deliberate design choice, not an accident.

**Repository:** https://github.com/RIKEN-RCCS/benchkit

Two things you'll do with it: **run/test a benchmark that already exists**,
or **contribute a new application or a new target system**. This skill
covers both. It does not cover maintaining BenchKit's own internals
(the result portal service, the estimation-package algorithms, CI
infrastructure) — see `docs/guides/developer-reference.md` in the repo for
that.

## Repository layout at a glance

```
benchkit/
├── programs/<code>/          # one directory per benchmark application
│   ├── build.sh               # required — builds the app for a given system
│   ├── run.sh                 # required — runs it, emits results
│   ├── list.csv                # required — which (system,nodes,...) to run
│   ├── estimate.sh             # optional — plugs into the estimation layer
│   └── README.md                # optional — app-specific notes
├── config/
│   ├── system.csv              # registered systems: mode, runner tags, queue
│   ├── queue.csv                 # scheduler submit-command templates
│   └── system_info.csv            # CPU/GPU/memory info, for portal display
├── scripts/
│   ├── bk_functions.sh          # sourced by every build.sh/run.sh
│   ├── job_functions.sh          # sourced helper: CSV lookups (system mode, queue_group, ...)
│   ├── test_submit.sh             # submit one list.csv row as a real batch job
│   ├── test_submit_build.sh        # build-only variant
│   ├── matrix_generate.sh           # list.csv × system.csv -> generated CI pipeline
│   ├── result.sh                     # results/result -> normalized Result JSON
│   ├── result_server/                 # send_results.sh, send_estimate.sh, api.sh
│   ├── site/                           # setup_runner.sh, preflight_runner.sh
│   └── estimation/                      # estimation pipeline driver/packages
├── docs/
│   ├── guides/add-app.md                 # full walkthrough, reference example: qws
│   ├── guides/add-site.md                 # full walkthrough for new systems
│   ├── guides/add-estimation.md            # routes to app-side vs package-side guides
│   └── cx/*.md                              # CX Framework specs (terminology, architecture)
└── result_server/                             # the result portal (Flask app; separate service)
```

## Running/testing an existing benchmark

There is no single `bin/benchkit` driver — you invoke the scripts for a
specific app/system pair directly.

**Local, no scheduler** (fastest iteration loop, useful for checking the
build/run logic itself works before touching a real job):

```sh
bash programs/<code>/build.sh <system>
bash programs/<code>/run.sh <system> <nodes> <numproc_node> <nthreads>
```

`run.sh` always takes exactly those four positional args, in that order,
regardless of application. Check `artifacts/` after the build step and
`results/result` after the run step.

**Real batch job on the target scheduler** (the actual "does this work in
CI" test):

```sh
bash scripts/test_submit.sh <code> <line_number>
```

`<line_number>` is the row in `programs/<code>/list.csv` to submit (1-based,
counting the header). This resolves `system`/`mode`/`queue_group` from
`config/system.csv`, prints them so you can sanity-check the resolution, and
submits through the right scheduler command for that system (PJM on
Fugaku-family systems, PBS on Miyabi-family, SLURM on R-CCS Cloud/RIKYU/etc.
— the mapping lives in `config/queue.csv`). `scripts/test_submit_build.sh`
is the build-only equivalent, and `scripts/test_estimate_submit.sh` tests
the estimation pipeline the same way.

**Generating the CI pipeline** (rarely needed by hand — CI runs this
itself, but useful to preview what a `list.csv` change will actually
schedule):

```sh
bash scripts/matrix_generate.sh [code=<c>] [system=<s>]
```

Reads `list.csv` × `system.csv`/`queue.csv`/`system_info.csv` and writes
`.gitlab-ci.generated.yml`.

## Contributing a new application

Reference example in the repo: `programs/qws/` (most fully built-out —
has build recipes for essentially every registered system). Full guide:
`docs/guides/add-app.md`.

1. **Branch and scaffold:**
   ```sh
   git checkout -b add-<code>
   mkdir programs/<code>
   ```
   (or `cp -pr programs/qws/ programs/<code>` to start from a real example).

2. **`list.csv`** — exact header, no more no less:
   ```csv
   system,enable,nodes,numproc_node,nthreads,elapse
   Fugaku,yes,1,4,12,0:10:00
   ```
   `enable` is `yes`/`no` (to disable a row, set `enable=no` — don't comment
   it out with `#`). Note `mode` and `queue_group` are **not** columns
   here — those come from `config/system.csv`, one shared source of truth
   across every app. Before adding a row for a system, confirm it already
   has entries in both `config/system.csv` and `config/system_info.csv`
   (if not, that's a site-registration task — see below, not something you
   do from the app side).

3. **`build.sh`** — receives `system` as `$1`. Pattern:
   ```sh
   #!/bin/bash
   set -euo pipefail
   system="$1"
   source scripts/bk_functions.sh

   bk_fetch_source "<git-url>" "<dest-dir>" "<branch-or-tag>"
   cd "<dest-dir>"

   case "$system" in
     Fugaku)   ... module loads, compiler flags, build commands ... ;;
     RC_GENOA) ... ;;
     *) echo "Unknown system: $system" >&2; exit 1 ;;
   esac

   cp <built-executable> "${PWD}/../artifacts/<name>"
   ```
   Always use `bk_fetch_source` rather than a raw `git clone` — it writes
   `results/source_info.env` with the repo/branch/commit hash, which is the
   provenance record the portal surfaces at `/results/usage`. Copy only the
   built executable (and anything else `run.sh` genuinely needs) into
   `artifacts/`, not the whole source/build tree — that's what CI archives.

   If the app needs input data files that live in the source tree you just
   cloned, stage them into `artifacts/` too (e.g. `cp data/<file>
   "${PWD}/../artifacts/<file>"`) rather than committing them under
   `programs/<code>/`. Large inputs in the repo raise clone/fetch cost for
   every pipeline; staging from the clone keeps the repo small and lets
   `run.sh` read them on the compute node even in cross-build mode. Record
   their upstream revision and SHA-256 checksums in a committed
   `programs/<code>/data/README.md` for provenance.

4. **`run.sh`** — receives `system nodes numproc_node nthreads` positionally.
   Pattern:
   ```sh
   #!/bin/bash
   set -euo pipefail
   system="$1"; nodes="$2"; numproc_node="$3"; nthreads="$4"
   source scripts/bk_functions.sh
   export OMP_NUM_THREADS="$nthreads"
   mkdir -p results && : > results/result

   case "$system" in
     Fugaku) mpiexec -n $((nodes*numproc_node)) ./artifacts/<name> ;;
     *) echo "Unknown system: $system" >&2; exit 1 ;;
   esac

   bk_emit_result --fom <value> --fom-unit <unit> --fom-version <label> \
     --exp <case-name> --nodes "$nodes" --numproc-node "$numproc_node" \
     --nthreads "$nthreads" >> results/result
   ```
   Verify success by grepping the application's own log output for a
   real completion marker — **not** just the launcher's exit code. A
   nonzero-but-silent-failure app can still return 0 from `mpiexec`;
   BenchKit's own convention (see `programs/salmon/run.sh` for a worked
   example) is to touch a marker file before the run, then check either
   the log or any output file newer than the marker for the expected
   success string before calling `bk_emit_result`.

5. **Result-line format** — what `bk_emit_result`/`bk_emit_section`/
   `bk_emit_overlap` (all in `scripts/bk_functions.sh`) append to
   `results/result`:
   ```
   FOM:5.752 FOM_unit:s FOM_version:DDSolverJacobi Exp:CASE0 node_count:1 numproc_node:4 nthreads:12
   SECTION:compute_kernel time:0.30
   SECTION:communication time:0.20
   OVERLAP:compute_kernel,communication time:0.05
   ```
   Minimum viable: just `--fom` + `--fom-unit`. `bk_emit_section`/
   `bk_emit_overlap` are optional finer-grained timing breakdowns (each
   takes `<name> <time> [package] [artifact]` positionally) — add them if
   the app naturally reports sub-phase timings (like SALMON's ground-state
   vs. real-time-propagation split), skip them otherwise.

6. **Optional: profiler data.** `bk_profiler` (in `bk_functions.sh`) wraps
   `fapp` (Fugaku, `--level single|simple|standard|detailed`) or `ncu`
   (NVIDIA, `--level ... --archive ... --raw-dir ... -- <cmd>`) and produces
   `results/padata<N>.tgz` archives BenchKit collects automatically.

7. **Test locally**, then via `scripts/test_submit.sh <code> <line_number>`
   (see above), then open a PR. **Commit message must include
   `[code:<code>]`** so CI scopes itself to just the new app; PR title
   convention is `Add new application: <code>`.

## Contributing a new site (target system)

Full guide: `docs/guides/add-site.md`. This is a two-part job: standing up
a GitLab Runner + Jacamar-CI pair on the target system under a normal user
account, then registering the system in BenchKit's config so apps can
target it.

**Fast path for the runner side** — `scripts/site/setup_runner.sh`
downloads GitLab Runner, builds Jacamar-CI, registers a frontend runner and
a Jacamar runner, and sets up a `systemd --user` service:

```sh
curl -fsSL https://raw.githubusercontent.com/RIKEN-RCCS/benchkit/main/scripts/site/setup_runner.sh | bash -s -- \
  --arch amd64 --site <your_site> --gitlab-url https://<your-gitlab-server> \
  --login-token "$LOGIN_RUNNER_TOKEN" --jacamar-token "$JACAMAR_RUNNER_TOKEN" \
  --scheduler pbs --service-host "$(hostname -s)"
```
`--scheduler` is one of `pbs|slurm|pjm`. Run `scripts/site/preflight_runner.sh`
first to check connectivity/proxy issues before this. `add-site.md` also
documents the fully-manual path (installing `gitlab-runner` at a pinned
version, building Jacamar-CI from source, writing `config.toml`/
`custom-config.toml` by hand) as a fallback/reference if the automated
script doesn't fit your site.

**Registering the system in config** — three CSVs, all in `config/`:

- **`system.csv`** (`system,mode,tag_build,tag_run,queue,queue_group`) —
  `mode` is `cross` (separate build/run nodes/runners) or `native` (same
  node); `tag_build`/`tag_run` are the GitLab runner tags you registered
  above (`tag_build` empty for `native`); `queue` keys into `queue.csv`
  (or `none` for login-node-only jobs).
  ```csv
  NewSystem,cross,newsystem_login,newsystem_jacamar,PBS_NewSystem,default
  ```

- **`queue.csv`** (`queue,submit_cmd,template`) — the scheduler submit
  command and its argument template. Template variables available:
  `${queue_group} ${nodes} ${numproc_node} ${nthreads} ${elapse} ${proc}`
  (= `nodes*numproc_node`), plus `${cpu_per_node} ${gpu_per_node}` pulled
  from `system_info.csv`.
  ```csv
  PBS_NewSystem,qsub,"-q ${queue_group} -l select=${nodes}:mpiprocs=${numproc_node}:ompthreads=${nthreads} -l walltime=${elapse}"
  ```

- **`system_info.csv`** (`system,name,cpu_name,cpu_per_node,cpu_cores,gpu_name,gpu_per_node,memory,display_order`)
  — purely for portal display and for the `${cpu_per_node}`/`${gpu_per_node}`
  template variables above. Use `-` where there's no GPU.

**Responsibility split to keep straight**: `system.csv` + `queue.csv` say
*where/how to submit*; `system_info.csv` says *how to display it*;
`programs/<code>/list.csv` says *what conditions to run for this app*;
`programs/<code>/{build,run}.sh` say *how to actually execute on that
system* (module loads, compiler, launcher, affinity) — a new site does not
require touching any app's `build.sh`/`run.sh` until you also want that app
to target it (that's back to "contributing a new application," per-app,
per-system `case` branch).

**Recommended verification order for a brand-new site** (from `add-site.md`):
1. source fetch reachable from the runner, 2) scheduler submit works at
all, 3) module load + build succeeds, 4) a run produces `results/result`,
5) `scripts/result.sh` turns it into valid Result JSON, 6)
`scripts/result_server/send_results.sh` succeeds. Debug in that order —
each stage assumes the previous one already works.

## Estimation and the result portal (pointers, not depth)

- **Estimation** (`docs/guides/add-estimation.md`) lets an app predict
  performance at scales/architectures you haven't directly measured, via
  an optional `programs/<code>/estimate.sh`. As an app contributor you
  only need the app-side guide (`add-estimation-to-app.md`) — you declare
  *what* sections exist and how to measure them; the estimation-package
  side (which algorithm extrapolates each section) is a separate
  maintainer role, not something you write per-app.
- **`result_server`** is the CX result portal — a separately-deployed Flask
  service that CI pushes results *into* (via
  `scripts/result_server/send_results.sh`); it's not something you run
  yourself as part of a normal build/run/contribute workflow. Results and
  estimates become browsable there automatically once `send_results.sh`
  succeeds in CI.

## Known gotchas

- **`list.csv`'s `enable` column, not `#` comments, disables a row.** A
  commented-out CSV row is easy to miss when `matrix_generate.sh` parses
  the file; `enable=no` is the explicit, grep-able way to keep a
  known-broken system/app combination out of CI without deleting the row.
- **Don't call a run successful just because the launcher exited 0.** Many
  HPC apps can silently produce garbage output (or hang and get killed by
  the scheduler with a misleading exit code) without the launcher itself
  reporting failure. Grep the app's actual log for a real completion
  marker before emitting a result — see `run.sh`'s pattern above.
- **`bk_fetch_source`, not raw `git clone`.** Skipping it means
  `results/source_info.env` never gets written, which breaks the
  source-provenance tracking the portal's `/results/usage` view depends
  on.
- **Don't commit large input data files under `programs/<code>/`.**
  They raise clone/fetch cost for every pipeline, including unrelated
  apps. If `bk_fetch_source` already clones the repo that ships the
  inputs, stage them into `artifacts/` from that clone and have `run.sh`
  read them from there; keep only metadata, provenance, URLs, and
  checksums in the repo.
- **A new system needs entries in *both* `system.csv` and
  `system_info.csv`** before any app's `list.csv` can reference it —
  `system_info.csv` isn't just cosmetic, `queue.csv` templates can
  reference `${cpu_per_node}`/`${gpu_per_node}` from it.
- **PR commit messages need a `[code:<code>]` tag** to scope CI to the
  relevant app instead of running the full matrix.
