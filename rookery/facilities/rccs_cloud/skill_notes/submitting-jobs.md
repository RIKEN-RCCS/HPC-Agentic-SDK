The R-CCS Cloud is a heterogeneous testbed with many partition families.
The two most important choices before writing any script are: **which
partition** (hardware family) and **which modules to load** (they differ
per partition).

## Workflow

1. **Pick the partition** — `get_facility(facility="rccs-cloud")` has the
   full table. Rules of thumb:
   - General x86_64 CPU work → `genoa` (default; EPYC, 768 GB) or `genoa-m` (3 TB)
   - Fujitsu A64FX (Arm) work → `fx700` (cross-compile from r340)
   - NVIDIA GPU (CUDA/nvhpc) → `a100`, `ai-l40s`, `qc-a100`, `qc-gh200`, `ng-dgx-m[0-3]`
   - AMD GPU (ROCm) → `mi100`, `qc-mi250`, `fs-mi300a`, `fs-mi300x`
   - Intel GPU (oneAPI) → `qc-pvc`
   - Cross-compilation for fx700 → `r340`
   - There is **no default partition** — unlike a single-partition
     facility, `attributes.queue_name` must always be set explicitly.

2. **Know the module for your partition** — every partition needs its own
   `system/<partition>` module loaded first. Put the module load at the
   start of `executable`. `source /etc/profile` is emitted automatically
   by the rendered script — do **not** add it manually.

   | Partition | Module command |
   |-----------|----------------|
   | fx700 | `module load system/fx700 FJSVstclanga` |
   | genoa, genoa-m | `module load system/genoa mpi/mpich-x86_64` |
   | a100 | `module load system/a100 nvhpc` |
   | b300 | `module load system/b300 nvhpc` |
   | ai-h100l-pu | `module load system/ai-h100l nvhpc` |
   | ai-h200-brc | `module load system/ai-h200-brc nvhpc` |
   | ai-l40s | `module load system/ai-l40s nvhpc` |
   | qc-a100 | `module load system/qc-a100 nvhpc` |
   | qc-gh200 | `module load system/qc-gh200 nvhpc` |
   | mi100 | `module load system/mi100 rocm` |
   | qc-mi250 | `module load system/qc-mi250 rocm` |
   | fs-mi300a | `module load system/fs-mi300a rocm` |
   | fs-mi300x | `module load system/fs-mi300x rocm` |
   | qc-pvc | `module load system/qc-pvc` (or `source /opt/intel/oneapi/setvars.sh`) |
   | ng-dgx-m[0-3] | `module load system/ng-dgx nvhpc` |
   | r340 | (none required) |

3. **Stage any needed files** with `fs_upload(facility="rccs-cloud", ...)` /
   `fs_mkdir(facility="rccs-cloud", ...)`.

4. **Submit with a JobSpec** via `submit_job(facility="rccs-cloud",
   spec=...)`.

   CPU MPI job on genoa (single node — see "MPI launch" below):
   ```json
   {
     "name": "my-cpu-job",
     "executable": "module load system/genoa mpi/mpich-x86_64 && mpirun -np 4 ./a.out",
     "directory": "/home/<user>/work",
     "resources": {"node_count": 1, "processes_per_node": 4},
     "attributes": {"duration": "01:00:00", "queue_name": "genoa"}
   }
   ```

   NVIDIA GPU job on ai-l40s (needs `--gpus=<n>`):
   ```json
   {
     "name": "my-gpu-job",
     "executable": "module load system/ai-l40s nvhpc && mpirun -np 2 ./app",
     "resources": {"node_count": 1, "gpus": 2, "processes_per_node": 2},
     "attributes": {"duration": "02:00:00", "queue_name": "ai-l40s"}
   }
   ```

   Superchip job on qc-gh200 (no GPU flag — the GPU is always present):
   ```json
   {
     "name": "my-gh200-job",
     "executable": "module load system/qc-gh200 nvhpc && srun ./app",
     "resources": {"node_count": 1},
     "attributes": {"duration": "01:00:00", "queue_name": "qc-gh200"}
   }
   ```

5. **Verify**: `get_job_status(facility="rccs-cloud", job_id=...)` right
   after submission — see `rccs-cloud-monitoring-jobs` for the sacct-lag
   caveat.

## MPI launch: use mpirun, not srun

This cluster's Slurm has **no PMI support**, so `srun` cannot bootstrap MPI
ranks — an MPI program launched with `srun` will hang or fail to start. Load
the MPI module, then launch with `mpirun` (OpenMPI) instead:
`module load system/genoa mpi/mpich-x86_64 && mpirun -np <n> ./a.out`.

This is also why most work here should **stay on a single node**: `mpirun`
without PMI needs its own hostfile/SSH-based remote launch for multi-node
jobs, which isn't set up on this cluster. Set `resources.node_count: 1` and
scale with `processes_per_node` unless you've separately confirmed a
multi-node `mpirun` launch works. (`srun` itself is still fine for
non-MPI/single-process work and interactive `srun --pty` sessions — the PMI
gap only affects MPI rank bootstrap.)

## fx700 (A64FX) affinity: bind processes to CMGs

fx700's 48 cores are **4 NUMA nodes ("CMGs") of 12 cores each**
(cores 0-11, 12-23, 24-35, 36-47 — confirmed via `numactl --hardware`).
Cross-CMG memory access is slower than local, so an MPI/hybrid job that
doesn't pin ranks to a CMG can land its processes anywhere, including
sharing or straddling CMGs. Verified live (real submitted job, `mpirun
--report-bindings`): request one rank per CMG and bind explicitly —

```
mpirun -np 4 --bind-to core --map-by numa:PE=12 ./app
```

This binds rank 0 to cores 0-11, rank 1 to 12-23, rank 2 to 24-35, rank 3 to
36-47 — one rank per CMG, matching the standard A64FX layout. For a
different rank count, keep `PE=<cores per rank>` so ranks still divide
evenly across CMGs (e.g. `-np 2 --map-by numa:PE=24` for 2 ranks/2 CMGs
each). **Be explicit even though OpenMPI's default binding sometimes lands
in the same place for a clean 4-rank job** — its default heuristic isn't
guaranteed for other rank counts, and an explicit `--map-by`/`--bind-to` is
self-documenting in the job script.

**This only works launched from a real submitted job — not from `mpirun`
nested inside an interactive `srun` shell.** An `srun ... bash -c 'mpirun
...'` wrapper under-reports available slots to OpenMPI ("not enough slots
available") because Slurm's task count, not `--cpus-per-task`, is what
`mpirun`'s Slurm integration reads. Always request
`resources.exclusive_node_use: true` on fx700 so the whole node's cores are
available to bind against:

```json
{
  "name": "fx700-hybrid-job",
  "executable": "module load system/fx700 FJSVstclanga && mpirun -np 4 --bind-to core --map-by numa:PE=12 ./app",
  "resources": {"node_count": 1, "processes_per_node": 4, "exclusive_node_use": true},
  "attributes": {"duration": "01:00:00", "queue_name": "fx700"}
}
```

For a single OpenMP-only process spanning the whole node (no MPI), set
`OMP_PROC_BIND=close OMP_PLACES=cores` in `environment` and make sure any
array initialization is done in a `parallel for` matching the compute
loop's split (first-touch) rather than serially from one thread — otherwise
all pages can land on one CMG's memory. Some run-to-run bandwidth variance
was observed on this shared cluster even with binding set, so treat single
process/48-thread runs as less predictable than the CMG-per-rank MPI
pattern above; prefer the latter when the workload allows it.

## R-CCS Cloud conventions

- **GPU flag**: set `resources.gpus` → the script emits `--gpus=<n>`, and
  `--nodes` is always emitted explicitly. Exception: `qc-gh200` and
  `ng-dgx-m[0-3]` are unified CPU+GPU superchips — leave `gpus` unset; the
  script emits no GPU flag for them and the GPU is present anyway.
- **Architecture matters**: `fx700` is A64FX (aarch64); `qc-gh200` and
  `ng-dgx` are NVIDIA Grace (aarch64). x86_64 binaries will not run on any
  of those. Cross-compile fx700 code on r340.
- **OS difference**: `ng-dgx-m[0-3]` runs Ubuntu; all others run Rocky
  Linux. A binary or wheel built for Rocky may need a rebuild for ng-dgx.
- **Network**: only InfiniBand partitions suit tightly-coupled multi-node
  MPI. Ethernet-only partitions have high latency; prefer single-node work
  there. Multi-node MPI is doubly discouraged here since it also needs a
  manual `mpirun` hostfile/SSH setup (see "MPI launch" above) — default to
  single-node.
- **Scripts land in `~/agent/jobs/`** — `fs_view(facility="rccs-cloud",
  path=...)` them to debug exactly what ran.
- **No account needed**: jobs without `--account` use your default Slurm
  account.

## R-CCS Cloud-specific don'ts

- Don't launch MPI ranks with `srun` — no PMI support; use `mpirun` instead.
- Don't submit an fx700 MPI/hybrid job without `--bind-to core --map-by
  numa:PE=<n>` on `mpirun` and `resources.exclusive_node_use: true` — see
  "fx700 affinity" above.
- Don't test `mpirun` by nesting it inside an interactive `srun` shell — it
  under-reports available slots. Submit a real job instead.
- Don't load a system module from the wrong partition.
