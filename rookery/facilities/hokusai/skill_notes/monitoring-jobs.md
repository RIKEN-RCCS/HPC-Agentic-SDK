## Fair-share is why a job waits

HBW2 orders jobs by **fair-share priority**, so a job can sit queued
because your project's recent usage is high, not because the cluster is
full. When a job is waiting, check both:

- `get_projects(facility="{{SLUG}}")` — your fair-share standing and raw
  usage per account (read live; it moves continuously).
- `get_resources(facility="{{SLUG}}")` — live partition occupancy.

## HBW2 failure modes and triage

- **No project / core-time exhausted** — check
  `get_projects(facility="{{SLUG}}")`; a project's new jobs stop starting
  once its allowance is spent.
- **Out of memory** (`native_state` OUT_OF_MEMORY) — raise the memory
  share, or move to the `lmc` partition (2.7 TiB nodes).
- **Hit wall time** (`native_state` TIMEOUT) — raise `duration`, or move
  from `mpc` (~24 h) to `mpc_l` (~72 h).
- **Threads unset** — not an error, a silent performance collapse: set
  `OMP_NUM_THREADS` to match `resources.cpu_cores_per_process`.
- **Conflicting MPI modules** — Intel MPI and Open MPI loaded together.
  Load one only; `module purge` before switching.
- **Exit 127, `error while loading shared libraries`** — the run job is
  missing a `module load` that the build used (MKL, Intel MPI); job shells
  start with a clean environment, so repeat the module loads at runtime.

Read the job's output and its `status.meta_data.native_state` together to
tell which of these it is. The exact submitted script is kept in
`~/agent/jobs/` — `fs_view(facility="{{SLUG}}", path=...)` it when
debugging.
