---
name: hot-memory
description: Measure per-kernel hot working sets, memory traffic, and FLOPs in MPI C/C++/Fortran codes for GPU memory planning. Use when the user asks about profiling, hot memory, working sets, GPU memory, memory bandwidth, FLOP/byte, or says "measure hot memory".
user-invocable: true
---

# Hot Memory — Per-Kernel Working Set Profiler

Hot Memory measures the **hot working set** of each kernel in an MPI
application — the actual bytes touched during execution, not just total
allocation. This is the key input for GPU memory planning.

It also measures memory traffic and FLOPs when hardware counters are
available, giving FLOP/byte ratios that classify kernels as memory-bound
or compute-bound.

**Analysis model: MPI-only.** OpenMP must be disabled or ignored. Build
with OpenMP disabled, or run with `OMP_NUM_THREADS=1` and interpret results
as MPI-only. Hardware counters only measure the main thread; the hot-byte
measurement is process-wide. Mixed MPI+OpenMP runs do not produce consistent
metrics.

---

## Prerequisites

The target machine must have:

- Linux (x86_64 or aarch64) — uses `/proc/self/clear_refs` and `/proc/self/smaps`
- An MPI compiler (`mpicc`, `mpif90`) and `make`
- PAPI (`libpapi-dev`) for FP and memory-traffic counting (optional: degrades
  gracefully to 0 FLOPs if unavailable)
- `perf` (`linux-tools-generic`) for hotspot discovery (optional: Phase 2
  is skipped if perf is unavailable)
- GCC, g++, gfortran

For the full feature set, an administrator may need to set:

```bash
sudo sysctl kernel.perf_event_paranoid=0
```

Hot-byte measurement (the core feature) works without this — it only needs
write access to `/proc/self/clear_refs`, which is available to regular users
on most Linux systems.

---

## Getting the profiler library

The profiler source is **bundled with this skill** in the `wss_profiler/`
directory next to this `SKILL.md` — it ships inside the
`RIKEN-RCCS/hpc-agentic-sdk` repository, so no download is needed. Copy it
into the project:

```bash
# <SKILL_DIR> = absolute path of the directory that contains this SKILL.md.
# The agent knows this path: it is the location it opened this skill from.
cp -r <SKILL_DIR>/wss_profiler wss_profiler
chmod +x wss_profiler/wss_check
```

Resolve `<SKILL_DIR>` to the absolute directory holding this `SKILL.md`
(e.g. `.../.crush/skills/hot-memory`, `.../.claude/skills/hot-memory`, or
wherever the skill was installed). The bundled `wss_profiler/` contains
`wss_profiler.h`, `wss_profiler.c`, `wss_profiler_f.c`,
`wss_profiler_mod.f90`, `wss_runtime_probe.c`, `wss_probe_fp_events.c`,
and the `wss_check` script.

Fallback only if the bundled `wss_profiler/` is absent (someone installed
just `SKILL.md` without the bundle) — fetch from the upstream mirror:

```bash
mkdir -p wss_profiler
BASE=https://raw.githubusercontent.com/william-dawson/hot-memory/main/wss_profiler
wget -P wss_profiler/ $BASE/wss_profiler.h
wget -P wss_profiler/ $BASE/wss_profiler.c
wget -P wss_profiler/ $BASE/wss_profiler_f.c
wget -P wss_profiler/ $BASE/wss_profiler_mod.f90
wget -P wss_profiler/ $BASE/wss_runtime_probe.c
wget -P wss_profiler/ $BASE/wss_probe_fp_events.c
wget -P wss_profiler/ $BASE/wss_check
chmod +x wss_profiler/wss_check
```

### Build the library and tools

```bash
cd wss_profiler
mpicc -DPROFILE_WSS -c wss_profiler.c   -o wss_profiler.o
mpicc -DPROFILE_WSS -c wss_profiler_f.c -o wss_profiler_f.o
mpif90 -c wss_profiler_mod.f90 -o wss_profiler_mod.o
ar rcs libwss_profiler.a wss_profiler.o wss_profiler_f.o wss_profiler_mod.o
cp wss_profiler_mod.mod . 2>/dev/null || true

gcc -O2 -o wss_probe_fp_events wss_probe_fp_events.c
mpicc -O2 -DPROFILE_WSS -o wss_runtime_probe wss_runtime_probe.c -L. -lwss_profiler -lpapi
cd ..
```

After this, `wss_profiler/` contains `libwss_profiler.a`, the `.h`/`.f90`
source, the `.mod` file, and the diagnostic binaries. Instrumented code
links against this library:

```
-I<project>/wss_profiler -L<project>/wss_profiler -lwss_profiler -lpapi
```

---

## Capability check

**Always run this first**, before any profiling. It tells you what this
machine can measure.

```bash
cd wss_profiler && PATH="$PWD:$PATH" ./wss_check
```

Or run the runtime probe directly for machine-readable output:

```bash
cd wss_profiler && PATH="$PWD:$PATH" mpirun -np 1 ./wss_runtime_probe
```

The probe reports KEY=VALUE lines:

| Key | Meaning |
|-----|---------|
| `HOT_BYTES_OK=1` | Hot-byte measurement works (the core feature) |
| `FP_OK=1` | FLOP counting works |
| `MEM_BYTES_OK=1` | Byte-based memory traffic (PAPI load/store) |
| `MEM_OK=1` | Some memory-access metric available |
| `FP_SOURCE` | `papi`, `perf_fallback`, or `none` |
| `WSS_PERF_FP_EVENTS_ENV` | The FP event codes that worked (e.g. `0x74,0x75`) |

### What to do with the result

- If `HOT_BYTES_OK=0`, the machine cannot write `/proc/self/clear_refs`.
  Profiling cannot proceed without root or elevated permissions.
- If `FP_OK=0` and `FP_SOURCE=none`, try discovering FP event codes:
  ```bash
  eval $(cd wss_profiler && PATH="$PWD:$PATH" ./wss_probe_fp_events 2>/dev/null)
  echo $WSS_PERF_FP_EVENTS
  ```
  On aarch64, the probe defaults to `0x74,0x75` (FP_FIXED_OPS_SPEC,
  FP_SCALE_OPS_SPEC). On other architectures, pass candidate codes from
  `perf list` and the CPU PMU reference manual.
- If FP event codes are found, **always inline them** in every command that
  runs the profiled binary:
  ```bash
  WSS_PERF_FP_EVENTS=0x74,0x75 mpirun -np 4 ./myapp
  ```
  Never use a separate `export` — each shell command is an independent
  session, and MPI launchers may strip inherited environment variables.
- Record the `env_prefix` (`WSS_PERF_FP_EVENTS=0x74,0x75` or empty) for
  use in every profiled run below.

---

## Workflow

### Prerequisite: Confirm baseline build and run

Before profiling, build the code normally and run it. Verify it exits
cleanly with the expected output. Do not proceed until the baseline works.

If the code has OpenMP support, disable it for the profiled run.

Use the project's own build system (`Makefile`, `CMakeLists.txt`, configure
script). Do not improvise a handwritten compile line unless the project has
no build system at all.

### Step 1: Baseline peak RSS

Run the unmodified binary under `/usr/bin/time -v` to measure peak RSS
(rank 0 only):

```bash
mpirun -np 4 /usr/bin/time -v ./myapp [args] 2>&1 | tee phase1_peak_memory.log
```

For MPI codes, wrap so only rank 0 is measured. A simple approach:

```bash
cat > /tmp/rank0_time.sh << 'EOF'
#!/bin/sh
if [ "$OMPI_COMM_WORLD_RANK" = "0" ]; then
  exec /usr/bin/time -v "$@"
else
  exec "$@" 2>/dev/null
fi
EOF
chmod +x /tmp/rank0_time.sh
mpirun -np 4 /tmp/rank0_time.sh ./myapp [args] 2>&1 | tee phase1_peak_memory.log
```

Parse `Maximum resident set size (kbytes)` and divide by 1024 to get MB.
This is the upper bound — per-kernel hot sets will be fractions of this.

**Check for warnings:** if the binary exits non-zero, runs in under 500ms,
or prints error patterns, diagnose before proceeding. Common causes: wrong
working directory, missing input file, silent crash.

### Step 2: Hotspot discovery (if perf is available)

If the capability check showed `perf_stat_ok`, sample the code to decide
which kernels to instrument:

```bash
mpirun -np 4 /tmp/rank0_time.sh perf record -e cycles -F 99 --call-graph=dwarf \
    -o /tmp/wss_perf.data -- ./myapp [args] 2>&1 | tee phase2_perf.log
perf report -n --stdio -i /tmp/wss_perf.data | head -200 > phase2_report.txt
```

Identify the top functions by sample percentage. Note which are in user
code vs. MPI/library code. Tell the user which functions appear hottest and
ask which to instrument, or make a recommendation based on the data.

If perf is not available, skip this step. Ask the user which kernels to
instrument, or read the source to identify the main compute loops.

### Step 3: Instrument, rebuild, and run

This step modifies the user's source code. **Ask permission before editing
files.** Explain which files and functions you plan to instrument and why
that granularity is appropriate.

#### Instrumentation (C/C++)

```c
#include "wss_profiler.h"

int main(int argc, char **argv) {
    MPI_Init(&argc, &argv);
    WSS_INIT();
    // ...

    WSS_BEGIN();
    matvec(A, p, Ap);
    WSS_END("matvec");

    WSS_BEGIN();
    precondition(M, r, z);
    WSS_END("preconditioner");
    // ...
}
```

Build with profiling:

```bash
mpicc -DPROFILE_WSS -I./wss_profiler -o myapp myapp.c -L./wss_profiler -lwss_profiler -lpapi
```

#### Instrumentation (Fortran)

```fortran
use wss_profiler_mod

call mpi_init(ierr)
call wss_init()

call wss_begin()
call matvec(A, p, Ap, ierr)
call wss_end_named("matvec")

call wss_begin()
call precondition(M, r, z, ierr)
call wss_end_named("preconditioner")
```

Build with profiling (note: `mpif90` does not search system paths for
`.mod` files — pass `-I` explicitly):

```bash
mpif90 -DPROFILE_WSS -I./wss_profiler -o myapp myapp.f90 -L./wss_profiler -lwss_profiler -lpapi
```

#### Profiled run

Run with the FP event prefix from the capability check inlined:

```bash
WSS_PERF_FP_EVENTS=0x74,0x75 mpirun -np 4 ./myapp [args] 2>&1 | tee phase3_run.log
```

If `WSS_PERF_FP_EVENTS` was empty (PAPI provides FP events, or no FP
counting available), omit the prefix.

**After the run, confirm the output does NOT contain `WSS_PERF_FP_EVENTS
not set`.** If it does, the inline prefix was missing from that command —
add it and rerun.

Parse the `[WSS]` lines from the log:

```
[WSS] matvec                    512.0 MB hot  1024.0 MB accessed   0.480 GFLOP  0.98 FLOP/B-hot  0.47 FLOP/B-acc
```

---

## Instrumentation strategy

### Granularity (the most important decision)

- **Too coarse** (wrap an entire solver): hot set ≈ peak allocation, not useful.
- **Too fine** (individual vector ops): noise dominates.
- **Goal**: find the level where distinct computational phases have
  meaningfully different working sets.

Process:
1. Read the source to understand the main loop structure and data access patterns.
2. Start coarse (one solver iteration). If hot set ≈ peak, go deeper.
3. Look for phase boundaries: before/after matvec, preconditioner, halo exchange.
4. For iterative solvers (CG, BiCGStab), the interesting level is usually
   individual operations within one iteration: matvec, preconditioner, dot
   products, vector updates.
5. Name measurements descriptively: `"matvec"`, `"preconditioner"`, not `"step1"`.

### Never nest WSS_BEGIN/WSS_END

The profiler uses a single global PAPI eventset and a single `clear_refs`
state. Nesting corrupts both. To measure at multiple levels, do **separate
runs**: one coarse, one fine.

### When built without -DPROFILE_WSS

All macros compile away to nothing. The same source file works for both
profiling and normal builds.

---

## How to interpret results

Each `[WSS]` line reports:

| Field | Meaning |
|-------|---------|
| `hot MB` | Unique pages touched — the GPU memory this kernel needs |
| `accessed MB` | Total bytes loaded+stored (0 if PAPI load/store unavailable) |
| `M accesses` | Memory-access event count (aarch64 PMU fallback when PAPI load/store unavailable) |
| `GFLOP` | Floating-point operations (0 if no FP counters) |
| `FLOP/B-hot` | FLOPs per byte of working set |
| `FLOP/B-acc` | FLOPs per byte of traffic (closest to roofline arithmetic intensity) |
| `FLOP/access` | FLOPs per memory-access event (aarch64 PMU fallback) |

When `accessed MB > hot MB`, the kernel revisits data (reuse ratio =
accessed/hot). When they're close, the kernel streams through data once.

### Results table format

Always include baseline peak RSS as context:

```
Peak memory (rank 0): 3072 MB

| Kernel        | % Time | Hot MB | % of Peak | Accessed MB | Reuse | GFLOP | FLOP/B-hot | FLOP/B-acc | Assessment   |
|---------------|--------|--------|-----------|-------------|-------|-------|------------|------------|--------------|
| stencil_apply |  42.3% |    512 |     16.7% |        1024 |  2.0x |  0.48 |       0.98 |       0.47 | memory-bound |
| fft_forward   |  28.1% |    128 |      4.2% |         256 |  2.0x |  0.19 |       1.57 |       0.74 | borderline   |
```

Show unavailable counter columns as "n/a" rather than 0. Hot MB and % of
Peak always work.

### FLOP/byte interpretation

- < 1: sweeps data with little reuse — almost certainly memory-bandwidth-bound
- 1–5: borderline — depends on hardware balance
- \> 10: compute-heavy — likely compute-bound

### Caveats to always state

- Hot bytes are at 4 KiB page granularity (rounded up). Small working sets
  have significant rounding error.
- Ignore OpenMP for analysis. Build with OpenMP disabled or run with
  `OMP_NUM_THREADS=1`.
- smaps includes stack, code, and library pages (~a few MB of noise).
  Negligible for large working sets.
- WSS measures rank 0 only. Assumes roughly symmetric workload across
  ranks. For load-imbalanced codes, measurements may undercount the busiest
  rank.

---

## GPU memory planning

### Key insight

**GPU memory planning is not about total allocation. It is about the
maximum hot working set across all kernels, plus what needs to stay
resident between them.**

### Will it fit on GPU X?

```
max_hot_mb = max(hot_mb across all profiled kernels)
device_mem_mb = <device memory in MB, e.g. 81920 for A100 80GB>

if max_hot_mb < device_mem_mb:
    "The heaviest kernel's working set is [max_hot_mb] MB, which fits in
     [device] memory ([device_mem_mb] MB). Total allocation is [total] GB
     but no single kernel needs all of it."
else:
    "The heaviest kernel ([name]) needs [max_hot_mb] MB, which exceeds
     [device] memory by [max_hot_mb - device_mem_mb] MB. Tiling or
     explicit swapping will be required."
```

### Transfer plan

Reason about execution order. For a time-stepping loop:
- **Data resident across transitions**: arrays hot in consecutive kernels
  stay on device.
- **Transfer cost of A → B**: `hot(B) - overlap(A,B)`, not `hot(B)`.
- **Minimum resident set**: union of arrays hot in kernels that must
  remain on device.

### Swap cost per timestep

```
swap_per_step ≤ sum(hot MB for all kernels in one timestep)   [worst case: no reuse]
swap_per_step ≥ max(hot MB)                                   [best case: all fits]
```

### Framing rules

- Never say "total allocation is X GB, so you need X GB of GPU memory."
  Always clarify hot set < total allocation.
- When you don't have array-level attribution, you can only bound overlap
  — say so.

---

## The wss_profiler library reference

### Macros (C/C++)

| Macro | Where | What it does |
|-------|-------|--------------|
| `WSS_INIT()` | Once, after `MPI_Init()` | Identifies rank 0, initialises PAPI |
| `WSS_BEGIN()` | Before each kernel call | Clears `/proc/self/clear_refs`, starts counters |
| `WSS_END("name")` | After each kernel call | Stops counters, reads smaps, prints `[WSS]` line |

Without `-DPROFILE_WSS`, all macros compile away to nothing.

### Fortran interface

```fortran
use wss_profiler_mod
call wss_init()
call wss_begin()
call some_kernel(...)
call wss_end_named("kernel_name")
```

### Why wss_profiler.c exists

The globals (`_wss_rank`, `_wss_eventset`, etc.) are declared `extern` in
the header so every translation unit shares one copy. Without this,
`WSS_INIT()` in `main.c` would set its own copy of `_wss_rank` while
`WSS_BEGIN()` in other files reads uninitialized copies and silently skips
all measurements.

### FP counting fallback chain

1. PAPI is tried first (`PAPI_DP_OPS`, `PAPI_SP_OPS`, then `PAPI_FP_OPS`).
2. If PAPI has no FP events, the profiler falls back to `perf_event_open`
   with raw PMU event codes from the `WSS_PERF_FP_EVENTS` environment
   variable (comma-separated hex codes, one fd per code, counts summed).
3. Use `wss_probe_fp_events` to discover which codes work on this machine.
4. If `WSS_PERF_FP_EVENTS` is not set and PAPI has no FP events, FLOPs = 0.

### Memory-access fallback (aarch64)

When PAPI load/store events are unavailable, the profiler falls back to
raw PMU `mem_access` events via `perf_event_open`. Set `WSS_PERF_MEM_EVENTS`
to a comma-separated list of hex event codes. On aarch64, defaults to
`0x13` (architectural MEM_ACCESS) if not set. Reports "M accesses" and
"FLOP/access" instead of "MB accessed" and "FLOP/B-acc".

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `WSS_PERF_FP_EVENTS not set` in profiled output | Env var not inlined on that command | Prefix inline: `WSS_PERF_FP_EVENTS=0x74,0x75 mpirun ...` — never use a separate export |
| All kernels report `0.000 GFLOP` despite capability check finding FP events | `env_prefix` not applied to that specific command | Re-run capability check, then immediately run profiled binary with the inline prefix |
| `0 GFLOP` and capability check showed no FP events at all | No PAPI and no working PMU codes | Run `eval $(./wss_probe_fp_events)` then re-run capability check with those codes |
| `perf record` fails with Permission denied | `perf_event_paranoid` too high | Skip Phase 2; proceed to Phase 3 if you know target kernels. Ask admin: `sudo sysctl kernel.perf_event_paranoid=0` |
| `cannot open /proc/self/clear_refs` | No write access to clear_refs | Run with root or elevated permissions (CAP_SYS_RESOURCE) |
| `mpirun: not enough slots` | OpenMPI slot detection broken | `OMPI_MCA_rmaps_base_oversubscribe=1` |
| 0 GFLOP even though `WSS_PERF_FP_EVENTS` is set | OpenMPI CPU binding pins rank 0 | Add `--bind-to none` to mpirun, or set `OMPI_MCA_hwloc_base_binding_policy=none` |
| Hot MB is 0 for all kernels | `clear_refs` write failed silently | Check the first `[WSS]` line for the error; ensure write access to `/proc/self/clear_refs` |

**Critical rule**: if you see `WSS_PERF_FP_EVENTS not set` or `0.000 GFLOP`
when you expected FP counting to work, **stop and diagnose** before
reporting results. Do not present 0 GFLOP as the answer if the capability
check found FP events.
