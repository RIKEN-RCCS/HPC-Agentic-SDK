---
name: fugaku-submitting-jobs
description: Submit and describe PJM jobs on Fugaku — resource group selection, node/elapse limits, project group, and MPI process shape.
---

# Submit Fugaku jobs

1. Choose a PJM resource group for `attributes.queue_name` — `small` (1–384
   nodes, up to 72h), `large` (385+ nodes, up to 24h), `int` (interactive),
   or a `spot-*` low-priority variant. Confirm the real min/max/default for
   the account with `run_command_on_cluster("pjacl --rg small")` if unsure.
2. Every job needs a project group: set `attributes.account` explicitly, or
   rely on `defaults.group` in `~/.hpc-agent/fugaku.json` (or
   `FUGAKU_GROUP`) — `submit_job` raises a clear error if neither is set.
   The shared `fugaku` group cannot submit jobs. If the resolved group is
   `trial` (the default "Startup Project" every new account gets), only the
   `spot-*` resource groups are usable — `small`/`large`/`int` will be
   rejected. Check `run_command_on_cluster("id")` for the account's real
   project groups before assuming `small` is available.
3. Fugaku has no GPUs — never set `resources.gpus` or
   `resources.gpu_cores_per_process`.
4. Set `resources.node_count`; for MPI work also set
   `resources.processes_per_node` (renders as PJM's
   `--mpi "max-proc-per-node=N"`) or `resources.process_count` for a total
   rank count. A `mpiexec -n <N>` launcher is added automatically whenever
   more than one task is requested — do not add it yourself unless you need
   non-default `mpiexec` flags (set `launcher` explicitly to override).
5. If the job touches storage outside `$HOME` (a group data volume, or
   Spack), set `attributes.custom_attributes["gfscache_volume"]` (e.g.
   `"/vol0004"`) or rely on the configured default — otherwise `pjsub` will
   reject the job.
6. Leave `stdout_path`/`stderr_path` unset — PJM has no flag for this; output
   always lands at `<name>.<job_id>.out`/`.err` in the submission directory
   (`~/agent/jobs/`).
7. Show the user the JobSpec (or the rendered script), then call
   `submit_job`. Inspect the stored script under `~/agent/jobs/` and poll
   with `get_job_status`.

Use `small` with a short `elapse` for validation jobs. Never run heavy
computation on the login node — submit a job instead.
