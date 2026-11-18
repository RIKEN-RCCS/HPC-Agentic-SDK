## RIKYU failure modes and triage

- **x86_64 binary on aarch64 nodes** → "Exec format error" in output.
- **OOM** → `native_state` OUT_OF_MEMORY; the fix is requesting more GPUs
  (each one brings 36 more CPU cores and ~400GB more memory as a fixed
  bundle — you can't raise memory independently of GPU count).
- **Time limit** → `native_state` TIMEOUT; raise `duration` (max 96h —
  there's no longer-running exception).
- **Lost scratch output** → results written to `/tmp` on the compute node
  but not copied back to `/home/<user>` or `/data1/<group>` before the job
  ended are unrecoverable.

The exact script that was submitted is kept in `~/agent/jobs/` —
`fs_view(facility="rikyu", path=...)` it when debugging.

## Live GPU utilization

For an ACTIVE job, check GPU usage on its node with:
`run_command_on_cluster(facility="rikyu", command="srun --overlap --jobid <id> nvidia-smi")`

Low utilization usually means a dataloader/CPU bottleneck or the job is
still in setup.
