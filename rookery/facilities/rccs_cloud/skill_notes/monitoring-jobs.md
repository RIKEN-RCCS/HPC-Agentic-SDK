> **sacct lag** (handled for you now): this cluster's `sacct` trails
> `sbatch` by a second or two, so `get_job_status` fired *immediately*
> after `submit_job` used to report the job as not found. `get_statuses`
> now falls back to `scontrol` for any id sacct doesn't yet know, which
> closes that window — a just-submitted job reports `queued` right away.
> No wait-and-retry needed; if you *do* still see "not found", treat it as
> a real unknown job id rather than a timing artifact.

## R-CCS Cloud failure modes and triage

- **Wrong architecture binary** → "Exec format error". x86_64 binaries
  sent to fx700, qc-gh200, or ng-dgx fail immediately; recompile for the
  target arch.
- **Missing/wrong system module** → command not found or link errors.
  Check `module load system/<partition>` is the first thing in
  `executable`.
- **OOM** → `native_state` OUT_OF_MEMORY; reduce ranks, set
  `resources.memory`, or move to a larger-memory partition (genoa-m).
- **Time limit** → `native_state` TIMEOUT; raise `duration` (ai-h100l-pu
  caps at 30 min).
- **GPU not allocated** → `nvidia-smi`/`rocm-smi` finds no devices. Set
  `resources.gpus` on partitions that need `--gpus=<n>` (not on
  superchips).
- **Wrong-partition module** → wrong ABI/segfaults. Match the
  `system/<partition>` module to the partition the job ran on.

The exact submitted script is kept in `~/agent/jobs/` —
`fs_view(facility="rccs-cloud", path=...)` it when debugging.

## Live job inspection

For an ACTIVE job on a GPU partition:
`run_command_on_cluster(facility="rccs-cloud", command="srun --overlap --jobid <id> nvidia-smi")` (NVIDIA)
`run_command_on_cluster(facility="rccs-cloud", command="srun --overlap --jobid <id> rocm-smi")` (AMD ROCm)
