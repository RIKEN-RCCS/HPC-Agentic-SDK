---
name: benchpark
description: Guide for using and contributing to Benchpark, a Spack+Ramble-based framework for specifying reproducible HPC benchmarks across multiple systems. Use when adding a benchmark to Benchpark, adding a target system/cluster, running or testing a Benchpark experiment, or understanding the experiment.py / ramble application.py / spack package.py / system.py layout. Generic framework guide — not specialized to any one application.
user-invocable: true
---

# Benchpark — reproducible HPC benchmark specifications

Benchpark (originally from LLNL) is a **specification** framework: it does
not build or run anything itself. You describe a benchmark's build (Spack),
run (Ramble), the experiment parameters, and the target system as code;
Benchpark assembles a Ramble workspace from those specs, then Spack builds
the code and Ramble runs and analyzes it. The payoff is reproducibility —
the same specs build and run the same way across sites.

**Upstream:** https://github.com/LLNL/benchpark
**RIKEN fork:** https://github.com/RIKEN-RCCS/benchpark (carries extra
system configs and apps; see "Branches" below)

Two things you'll do with it: **run an existing benchmark**, or **contribute
a new benchmark or target system**. This skill covers both, generically. It
does not cover maintaining Benchpark's own framework internals.

## The four layers of one benchmark

Every benchmark in Benchpark is the composition of four files. Learn this
shape — it's exactly what you add or edit when contributing.

```
experiments/<benchmark>/experiment.py              # 1. experiment
repos/ramble_applications/<benchmark>/application.py   # 2. ramble app (run + FOM)
repos/spack_repo/benchpark/packages/<benchmark>/package.py  # 3. spack package (build)
                                                    #   + optional *.patch files
systems/<site>/system.py                            # 4. system (per-site compilers/externals)
```

What each layer owns:

1. **`experiment.py`** — *which run, on how many resources, with which
   params.* A class inheriting `Experiment` plus a `ProgrammingModel(...)`
   mixin declaring supported models (`Mpionly`, `Openmp`, `Cuda`, `Rocm`),
   optionally `Scaling(ScalingMode.Strong, ScalingMode.Weak, ...)`, and
   optionally `Caliper`. Declares `variant("workload")`, `variant("version")`,
   and `maintainers("ghuser")`. The body is two methods:
   - `compute_applications_section()`: sets at least one of
     `n_nodes`/`n_ranks`/`n_gpus` (required — Benchpark can't allocate
     resources otherwise), `n_threads_per_proc`, the workload's input
     parameters, and **must** call `set_required_variables(n_resources=,
     process_problem_size=, total_problem_size=)` (all three are required
     metadata for Benchpark's bookkeeping — they are *not* Ramble variables).
     Can branch on `self.system_spec.name` / `self.system_spec.variants`
     for per-system config. `exec_mode=test|perf` is a built-in variant for
     a small validation run vs. the real performance run.
   - `compute_package_section()`: `self.add_package_spec(self.name,
     [f"{name}{self.determine_version()}"])`.

2. **`application.py`** (Ramble `ExecutableApplication`) — *how to run and
   how to extract the figure of merit.* Defines `executable("name",
   "<cmd>", use_mpi=True/False)` (often one for input prep, one for the
   run, optionally one to compute the FOM), a `workload("name",
   executables=[...])`, `workload_variable("X", default="...")`,
   `environment_variable("OMP_NUM_THREADS", "{n_threads_per_proc}", ...)`,
   `success_criteria("id", mode="string", match=<regex>, file=<log>)`, and
   `figure_of_merit("id", fom_regex=r"...(?P<grp>...)", group_name="grp",
   log_file="<path>", units="...")`. **The FOM is a regex over a log file**,
   not an inline computation — if the app doesn't already write the number
   you want to a log, add a small `executable` that runs a parser (python,
   awk) to produce a `.dat` file the regex then reads (mVMC's `compute-fom`
   is the canonical example).

3. **`package.py`** (Spack recipe — `CMakePackage`, `MakefilePackage`, etc.)
   — *how to build.* `version('x', sha256='...')`, `variant(...)`,
   `depends_on('mpi')`/`('blas')`/etc., `cmake_args()`, `install()`. If
   upstream Spack already has the package, Benchpark uses that unless you
   add one here to override. Optional `*.patch` files live alongside
   `package.py`.

4. **`system.py`** — *the target site's compilers, scheduler, and external
   libraries.* A `System` subclass with `id_to_resources` (per-cluster
   `sys_cores_per_node`/`sys_gpus_per_node`/`sys_mem_per_node_GB`/`queue`/
   `hardware_key`), `variant("cluster", ...)`, `variant("compiler", ...)`,
   `compute_packages_section()` (Spack `packages:` with externals + paths),
   and `compute_compilers_section()` (`compiler_section_for`/`compiler_def`).
   **This is where module-load equivalents and compiler/library paths live** —
   *not* inline in the experiment.

## Running an existing benchmark

```sh
git clone https://github.com/LLNL/benchpark.git && cd benchpark
. setup-env.sh                       # bootstraps Spack + Ramble into a venv
benchpark --version                  # sanity check

# 1. initialize the target system
benchpark system init --dest=mysys <SystemName> compiler=<c> [cluster=<x>]

# 2. initialize the experiment (variants as CLI args)
benchpark experiment init --dest=myexp mysys <Benchmark> +openmp workload=<w>

# 3. assemble the Ramble workspace
benchpark setup mysys/<Benchmark> <workspace_path>
. <workspace_path>/setup.sh

# 4. build (Spack) and run (Ramble)
cd <workspace_path>
ramble --workspace-dir . workspace setup    # Spack builds the benchmark
ramble --workspace-dir . on                 # runs all experiments in the workspace
ramble --workspace-dir . workspace analyze  # FOMs + success/fail summary
```

`<SystemName>` and `<Benchmark>` are the names from `benchpark list systems`
/ `benchpark list benchmarks`. Variants on `experiment init` take the form
`+openmp`/`~cuda` (boolean) or `workload=problem1`/`version=develop`
(string); built-ins include `exec_mode=test|perf`, `scaling-factor`,
`scaling-iterations`, `package_manager` (e.g. `user-managed` to use a
pre-built binary via `prepend_path=/path/to/bin`), `n_repeats`, and
`timeout`.

To run a **single** experiment rather than all: invoke its
`execute_experiment` script directly, e.g.
`$workspace/experiments/<bench>/<problem>/<exp_name>/execute_experiment`.

## Discovering what exists

```sh
benchpark list                          # benchmarks, systems, experiments
benchpark list systems                  # all systems (see docs/system-list.rst)
benchpark list benchmarks               # all benchmarks (docs/benchmark-list.rst)
benchpark list experiments
benchpark list modifiers                # affinity, caliper, hwloc, allocation, ...
benchpark info system <system>         # full detail on one system
benchpark info experiment <experiment> # full detail on one experiment
benchpark tags -a application <app>     # tags for an application
```

## Contributing a new benchmark

Reference examples in the repo: `experiments/amg2023/experiment.py` (full
features — multi programming model, scaling, Caliper) and
`experiments/test/saxpy/experiment.py` + `repos/ramble_applications/saxpy/
application.py` (minimal). The docs walkthrough is
`docs/add-an-experiment.rst` (uses HPL) and `docs/add-a-benchmark.rst`.

1. **`experiments/<benchmark>/experiment.py`** — start from a copy of a
   similar experiment. Set the right `ProgrammingModelType`s. Add
   `variant("workload")` and `variant("version", values=(...),
   default=...)`. Add `maintainers("yourgh")`. In
   `compute_applications_section()`, set the resource variables (at least
   one of `n_nodes`/`n_ranks`/`n_gpus`), `n_threads_per_proc`, the workload
   input params, and the three required `set_required_variables`. In
   `compute_package_section()`, add the package spec.

2. **`repos/ramble_applications/<benchmark>/application.py`** — define the
   `executable`s, `workload`, `workload_variable`s, `environment_variable`s,
   `success_criteria` (regex on a log file), and `figure_of_merit`s. If
   upstream Ramble already defines the app, Benchpark uses that unless you
   add one here.

3. **`repos/spack_repo/benchpark/packages/<benchmark>/package.py`** — a
   Spack recipe with `version(..., sha256=...)`. If upstream Spack already
   has the package, Benchpark uses that unless you add one here. Add
   `*.patch` files alongside if the source needs patching.

4. **No new `system.py`** unless the target site is absent — reuse an
   existing system and add a `cluster` variant value + `id_to_resources`
   entry (see "Contributing a system" below).

**Validate before opening a PR** (per `docs/testing-your-contribution.rst`):
```sh
benchpark system init --dest=mysys <SystemName> compiler=<c>
benchpark experiment init --dest=myexp mysys <benchmark>
# CI auto-runs "dryrunexperiments" on PRs — these do NOT build or run;
# they verify the experiment/system initializes and the required variables
# exist. A maintainer approves CI for first-time contributors.
```
The doc explicitly encourages upstreaming the `package.py` to Spack and the
`application.py` to Ramble once the experiment is working, then removing
the copy from `repos/` — `repos/` is a staging area.

## Contributing a new system / cluster

Follow `docs/add-a-system-config.rst`. First check whether a system with
the same hardware already exists (`docs/system-list.rst`,
`systems/all_hardware_descriptions/`):

- **Same hardware + software stack exists** → add your cluster as a value
  under that system's `cluster` variant and add an `id_to_resources` entry.
  No new file.
- **Same hardware, different software stack** → likely still parameterize
  the existing `system.py`.
- **No hardware match** → add a hardware description under
  `systems/all_hardware_descriptions/<name>/` (naming:
  `[INTEGRATOR][-MICROARCH][-ACCELERATOR][-NETWORK]`) and a new
  `systems/<site>/system.py`.

Per-cluster compiler paths, module equivalents, and library externals go
in `compute_packages_section`/`compute_compilers_section` of `system.py` —
**not** in the experiment. This centralizes site knowledge per site, the
opposite of a per-app inline approach.

## What to rerun after editing (from `docs/FAQ.rst`)

| Changed | Rerun |
|---|---|
| configs | `ramble --workspace-dir . workspace setup` |
| benchmark's `package.py` or a dependency | `ramble --workspace-dir . workspace setup` |
| experiment parameters | delete `workspace/experiments` |
| wish to rerun experiments | delete `workspace/experiments` |

## Modifiers (pointers)

Modifiers (`modifiers/`: `affinity`, `caliper`, `hwloc`, `allocation`)
inject reusable patterns — e.g. `affinity=on` at `experiment init` adds a
small separate run that records thread/GPU affinity to a file; `caliper`
adds Caliper profiling. See `docs/modifiers.rst`.

## Gotchas

- **The FOM is a regex on a log file**, not a computed value. If your app's
  metric isn't already in a log, add a compute `executable` that parses the
  app's output and writes a small `.dat` file, then point `figure_of_merit`
  at it.
- **`set_required_variables` is mandatory** — `n_resources`,
  `process_problem_size`, `total_problem_size` are all required even though
  they're metadata, not Ramble variables. Pick per-process vs total
  problem size to match how the app defines problem size (see
  `amg2023` for per-process, `kripke` for total).
- **At least one of `n_nodes`/`n_ranks`/`n_gpus` must be set** or Benchpark
  can't allocate resources.
- **`+openmp` requires the Spack package to define an openmp variant.** If
  it doesn't, keep the experiment `Mpionly` and set threading via an
  `OMP_NUM_THREADS` `environment_variable` in the ramble app instead.
- **`repos/` is the override location, not `repo/`.** The actual layout is
  `repos/ramble_applications/<bench>/` and
  `repos/spack_repo/benchpark/packages/<bench>/` (some older docs/FAQ
  text says `benchpark/repo/<bench>/` — that's the upstream LLNL layout).
  `config/repos.yaml` declares these search paths.
- **dryrun CI does not build or run** — passing it only means the spec
  initializes. Real build/run validation is on you or a maintainer's
  hardware.
- **`checkout-versions.yaml` pins Spack/Ramble** — the latest upstream
  Spack/Ramble features or packages may lag in Benchpark. You can
  temporarily copy a needed package into `repos/` to get ahead of this.

## Branches (RIKEN fork)

The RIKEN-RCCS fork carries RIKEN system configs and apps on **branches**,
not all on `develop`. Always check branches before concluding an app or
system is absent:
```sh
git ls-tree -r --name-only origin/<branch> | grep -i <name>
```
`develop` tracks upstream plus some RIKEN additions. Confirm where a
specific contribution belongs before branching off it.

## BenchKit vs Benchpark (companion skill)

BenchKit (shell-first, same RIKEN ecosystem) and Benchpark
(Spack+Ramble, structured) are complementary, not redundant:

| | BenchKit | Benchpark |
|---|---|---|
| Build/run | shell `build.sh`/`run.sh` you read by hand | Spack builds, Ramble runs (generated) |
| Where site modules/compilers live | inline per-app per-system `case` block | `system.py` `compute_*_section` (per-site) |
| Adding an app | `programs/<code>/{build,run}.sh,list.csv}` | 4 files (experiment + ramble app + spack pkg + maybe system) |
| FOM | `bk_emit_result --fom ...` → `results/result` | `figure_of_merit(...)` regex on a log file |
| Verification | `scripts/test_submit.sh` real batch job | dryrun CI (init only) + manual build/run |

Keep site-level compiler/library facts in Benchpark's `system.py` and
app-level run recipes in BenchKit's shell files; keep the two consistent
with what you have actually verified.

## Further reading (in a benchpark clone's `docs/`)

- `for-the-impatient.rst` — the 5-command run loop.
- `add-an-experiment.rst` — full `experiment.py` walkthrough (HPL).
- `add-a-benchmark.rst` — `package.py` + `application.py` prerequisites.
- `add-a-system-config.rst` — `system.py` + hardware descriptions.
- `testing-your-contribution.rst` — dryrun CI + manual validation.
- `benchpark-commands.rst` — `benchpark list`/`info`/`tags` reference.
- `run-binary.rst` — using a pre-built binary (`package_manager=user-managed`).
- `modifiers.rst` — `affinity`, `caliper`, `hwloc`, `allocation`.
- `FAQ.rst` — what to rerun after edits, Spack/Ramble version pinning.
