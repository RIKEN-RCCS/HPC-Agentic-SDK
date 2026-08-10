# Skill: fugaku-build

Guide for building HPC applications on Fugaku (A64FX). Documents four verified compiler toolchains, the BLAS/LAPACK interoperability story, how to prove your build actually produces working parallel code, and common gotchas.

## Compiler summary

| toolchain | C++ wrapper | MPI version | BLAS/LAPACK | verified? |
|---|---|---|---|---|
| Fujitsu TCS/DSP 1.2.43 (default) | `mpiFCCpx` | Fujitsu MPI 3.1 | SSL2 (static `.a`) | ✅ yes — baseline |
| GCC cross 11.2.1 | `mpiFCCpx`¹ | Fujitsu MPI 3.1 | Spack OpenBLAS `.so` | ⚠️ builds correctly; runtime LD_LIBRARY_PATH gotcha (see below) |
| LLVM/Clang 22.1.0 | `mpiclang++` | Fujitsu MPI 3.1 | Spack OpenBLAS `.so`, or experimental `fjlapack(ex)sve` (see below) | ✅ yes — runtime needs `libomp.so` in `LD_LIBRARY_PATH` |
| Spack GCC 15.1.0 + OpenMPI + OpenBLAS | `mpicxx` | Spack OpenMPI 5.0.8 | Spack OpenBLAS `.so` | ⚠️ configure+build ok, OpenMPI is aarch64-only on login node |

¹ After GCC cross activation, `mpiFCCpx -show` reveals the actual cross compiler underneath while keeping Fujitsu MPI wrapper flags.

## The SSL2 interoperability rule

Fujitsu's SSL2 BLAS/LAPACK is **ABI-incompatible with GCC and Clang**. It uses a different Fortran name-mangling convention (`dsyev` vs `dsyev_`). If CMake's `FindBLAS` locates `libssl2mpi.a` during a GCC/Clang configure, configuration succeeds but the link step fails with:

```
undefined reference to 'dsyev_'
```

**Fix:** Use Spack OpenBLAS instead. It exports standard mangled symbols and both GCC and LLVM link against it cleanly. Under LLVM specifically, there's also a second option — Fujitsu's own `fjlapacksve`/`fjlapackexsve` libraries, a separate build from SSL2 proper — see "Fujitsu math libraries with LLVM (experimental)" under the LLVM/Clang section below.

---

## Fujitsu TCS/DSP 1.2.43 (default)

Loaded by default on login and compute nodes.

| tool | path |
|---|---|
| C++ compiler | `/opt/FJSVxtclanga/tcsds-1.2.43/bin/mpiFCCpx` |
| C compiler | `/opt/FJSVxtclanga/tcsds-1.2.43/bin/mpifccpx` |
| Fortran compiler | `/opt/FJSVxtclanga/tcsds-1.2.43/bin/mpifrtpx` |
| SSL2 | `/opt/FJSVxtclanga/tcsds-1.2.43/lib64/libssl2mpi.a`, `libssl2mpisve.a`, `libssl2mt.a` |

**Wrapper name convention:** The `px` suffix means *cross* — these are login-node wrappers that target A64FX. On compute nodes, the same compilers are available **without** the `px` suffix: `mpiFCC`, `mpifcc`, `mpifrt`. However, **you should not build on compute nodes**. Cross-compile on the login node with `*px` wrappers, then submit the binary to compute nodes. Building inside a `pjsub` job is an anti-pattern — compute nodes have limited toolchain mounts and slower filesystems.

### Key flags

- `-Kfast` — Fujitsu's aggressive optimization (equivalent to `-O3` + architecture-specific tuning for A64FX)
- `-Kopenmp` — enable OpenMP
- `-Nclang` — switch the compiler frontend to Clang mode (if your code needs it; default mode is Fujitsu own)
- `-Nlibomp` — link against LLVM OpenMP runtime instead of Fujitsu's (rarely needed)

### Quick build example

```sh
# Verify what compiler is actually being invoked
mpiFCCpx -show

# Build with aggressive optimization + OpenMP
/opt/FJSVxtclanga/tcsds-1.2.43/bin/mpiFCCpx -Kfast -Kopenmp \
  main.cpp -o myapp -lpthread
```

**Build on login node, run on compute nodes:** The `*px` wrappers exist on the login node for cross-compilation. A compute-node `pjsub` job should **run the pre-built binary**, not compile. If you must use a compiler inside a job (e.g. for JIT or test suites), use the compute-node native names (`mpiFCC`, `mpifcc`, `mpifrt`) or add the TCS `bin` directory to `PATH`:

```sh
export PATH="/opt/FJSVxtclanga/tcsds-1.2.43/bin:${PATH}"
```

But in practice, compile-time on compute nodes is slower and the filesystem is shared — cross-compile on the login node and submit the binary instead.

With CMake:

```sh
cmake -S . -B build/fugaku -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_COMPILER=mpiFCCpx
```

CMake's `FindBLAS` / `FindLAPACK` succeed automatically against SSL2. No manual `LD_LIBRARY_PATH` needed at runtime.

---

## GCC cross 11.2.1

Three versions under `/vol0004/apps/oss/gcc-arm-*`:

- `gcc-arm-8.3.0` (old)
- `gcc-arm-10.3.1`
- **`gcc-arm-11.2.1`** (recommended — newest, used for verification)

Activate:

```sh
source /vol0004/apps/oss/gcc-arm-11.2.1/setup-env.sh
```

**Version quirk:** `mpiFCCpx --version` still prints `GCC 8.5.0` after activation, but `mpiFCCpx -show` reveals the actual cross compiler is `/opt/FJSVxos/devkit/aarch64/bin/aarch64-linux-gnu-g++` (GCC 11.2.1). The printed version is the *local* x86_64 side tool; the cross compiler is what compiles.

### Quick build example

```sh
source /vol0004/apps/oss/gcc-arm-11.2.1/setup-env.sh

/opt/FJSVxtclanga/tcsds-1.2.43/bin/mpiFCCpx -O3 -fopenmp \
  main.cpp -o myapp -lpthread
```

The wrapper (`mpiFCCpx`) transparently swaps to the cross GCC while keeping Fujitsu MPI include/library flags.

**Fortran wrapper note:** `mpifrtpx` (Fujitsu Fortran MPI wrapper) also transparently swaps to `aarch64-linux-gnu-gfortran` after GCC cross activation. This means you can build Fortran MPI code with the same wrapper for both Fujitsu-native and GCC-cross configurations, just varying the flags (`-Kfast` vs `-O3`).

### With CMake + Spack OpenBLAS

```sh
source /vol0004/apps/oss/gcc-arm-11.2.1/setup-env.sh

OB="/vol0004/apps/oss/spack-v1.0.1/opt/spack/linux-a64fx/\
openblas-0.3.30-tayl3edqrmltxa7fylvolkjwg4rvj3gg/lib/libopenblas.so"

cmake -S . -B build/gcc-cross -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_COMPILER=mpiFCCpx \
  -DBLAS_LIBRARIES="${OB}" -DLAPACK_LIBRARIES="${OB}"
```

---

## LLVM/Clang 22.1.0

Load the module:

```sh
module load LLVM/llvmorg-22.1.0
```

Wrappers installed:

- `mpiclang++` — C++
- `mpiclang` — C

These call `clang++`/`clang` and inject Fujitsu MPI paths from `/vol0004/apps/r/OSS_CN/llvm-22.1.0/fj-mpi/cross_mpi/`.

### Quick build example

```sh
module load LLVM/llvmorg-22.1.0

/vol0004/apps/r/OSS_CN/llvm-22.1.0/fj-mpi/cross_mpi/bin/mpiclang++ \
  -O3 -fopenmp main.cpp -o myapp -lpthread
```

### With CMake + Spack OpenBLAS

```sh
module load LLVM/llvmorg-22.1.0

OB="/vol0004/apps/oss/spack-v1.0.1/opt/spack/linux-a64fx/\
openblas-0.3.30-tayl3edqrmltxa7fylvolkjwg4rvj3gg/lib/libopenblas.so"

cmake -S . -B build/llvm-cross -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_COMPILER=mpiclang++ \
  -DBLAS_LIBRARIES="${OB}" -DLAPACK_LIBRARIES="${OB}"
```

### Fujitsu math libraries with LLVM (experimental)

An alternative to Spack OpenBLAS: Fujitsu's compiler manual (§3.3.3, "How to use math libraries of Fujitsu Compiler") documents linking Fujitsu's own BLAS/LAPACK directly under LLVM. **This is a different library from SSL2** (`libssl2mpi.a` etc., covered above) — SSL2 itself is ABI-incompatible with Clang; `fjlapacksve`/`fjlapackexsve` are a separate build that Fujitsu documents specifically as working with LLVM. Marked "experimental" by Fujitsu themselves, and use of Fujitsu-compiler-provided libraries with other compiler environments is explicitly **not supported** by Fujitsu — if you hit runtime issues, fall back to Spack OpenBLAS instead.

Two variants:

- `-lfjlapacksve` — BLAS + LAPACK, serial
- `-lfjlapackexsve` — BLAS + LAPACK, multi-threaded

```sh
module load LLVM/llvmorg-22.1.0

INCLUDE="-idirafter /opt/FJSVxtclanga/tcsds-latest/include"
LIBS="-L /opt/FJSVxtclanga/tcsds-latest/lib64"
FLIB="-lfjlapacksve -lfj90i -lfj90f -lfjsrcinfo -lfjcrt -lelf"                                    # serial
FLIB_M="-lfjlapackexsve -lfjomphk -lfjomp -lfj90i -lfj90f -lfjsrcinfo -lfjcrt -lfjompcrt -lelf"   # multi-threaded

clang++ -O2 sample.cpp ${INCLUDE} ${LIBS} ${FLIB}
clang++ -O2 sample.cpp ${INCLUDE} ${LIBS} ${FLIB_M}
flang -O2 sample.f ${LIBS} ${FLIB}
flang -O2 sample.f ${LIBS} ${FLIB_M}
```

**Verified (link-time only, this session):** both `${FLIB}`/`${FLIB_M}` variants confirmed against a real `dgemm_` call — `clang++` links cleanly with `LLVM/llvmorg-22.1.0` loaded, and `/opt/FJSVxtclanga/tcsds-latest/{include,lib64}` and both libraries exist at the documented paths. Output is a valid aarch64 ELF cross-binary, same as every other LLVM build in this section — run it on a compute node, not the login node. Runtime correctness (does `dgemm_` actually produce right answers under this link) was **not** verified — Fujitsu's own text only claims the link step, and says to discontinue use if runtime issues appear.

**Runtime note:** The LLVM OpenMP runtime (`libomp.so`) is **not** in the default compute-node library search path. You must add it to `LD_LIBRARY_PATH` in your job script:

```sh
export LD_LIBRARY_PATH="/vol0004/apps/r/OSS_CN/llvm-22.1.0/cross_clangfx/lib64:\
${LD_LIBRARY_PATH}"
```

Without this, any OpenMP-enabled LLVM binary fails at startup with `error while loading shared libraries: libomp.so`.

---

## Spack toolchain (advanced)

Spack is available at `/vol0004/apps/oss/spack-v1.0.1/`.

```sh
source /vol0004/apps/oss/spack/share/spack/setup-env.sh
```

Useful packages on Fugaku (`linux-rhel8-a64fx`):

- `openblas@0.3.30` (built with `fj@4.12.0`, `fj@4.12.1`, `gcc@15.1.0`)
- `openmpi@5.0.8` (built with `gcc@15.1.0`)
- `mpich-tofu@1.0` (Tofu-optimized MPICH)
- `gcc@15.1.0` as a native aarch64 compiler

**Login-node limitation:** Spack OpenMPI's `mpicxx` is an **aarch64 binary**. On the x86_64 login node it fails with:

```
cannot execute binary file: Exec format error
```

This means CMake configuration fails if it tries to execute the wrapper to probe compiler features. Workarounds:

1. **Use Fujitsu MPI wrappers** (`mpiFCCpx`, `mpiclang++`) and only borrow Spack OpenBLAS for math libraries. This is the simplest path.
2. **Configure on a compute node** — submit a short batch/interactive job on a compute node and build there.
3. **Use a CMake toolchain file** that avoids executing the wrapper at configure time.

---

## Verifying your build actually works

A binary that compiles and links is not enough on a cross-compilation system. You need to prove:

1. **MPI** works *across nodes* (not just localhost on the login node)
2. **OpenMP** uses the expected number of threads
3. **Optimization flags** actually affect performance

### Minimal verification program

Save as `verify.cpp`:

```cpp
#include <mpi.h>
#include <omp.h>
#include <iostream>
#include <vector>
#include <chrono>
#include <unistd.h>
#include <cmath>

int main(int argc, char** argv) {
    MPI_Init(&argc, &argv);
    int rank, size;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &size);

    char hostname[256];
    gethostname(hostname, sizeof(hostname));

    int nthreads = 0;
    double omp_sum = 0.0;
    #pragma omp parallel reduction(+:omp_sum)
    {
        #pragma omp single
        nthreads = omp_get_num_threads();
        omp_sum += 1.0;
    }

    // Compute kernel that optimization flags can act on
    int N = 256;
    std::vector<double> A(N*N, 1.0), B(N*N, 2.0), C(N*N, 0.0);
    auto t0 = std::chrono::high_resolution_clock::now();
    #pragma omp parallel for collapse(2)
    for (int i = 0; i < N; ++i) {
        for (int j = 0; j < N; ++j) {
            double sum = 0.0;
            for (int k = 0; k < N; ++k) {
                sum += A[i*N + k] * B[k*N + j];
            }
            C[i*N + j] = sum;
        }
    }
    auto t1 = std::chrono::high_resolution_clock::now();
    double compute_ms = std::chrono::duration<double, std::milli>(t1 - t0).count();

    // Verify MPI across ranks
    double local_val = rank + 1.0;
    double global_val = 0.0;
    MPI_Allreduce(&local_val, &global_val, 1, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);

    double expected_c = 2.0 * N;
    bool compute_ok = (std::abs(C[0] - expected_c) < 1e-12);
    double expected_reduce = size * (size + 1) / 2.0;
    bool mpi_ok = (global_val == expected_reduce);
    bool omp_ok = (nthreads == omp_get_max_threads());

    if (rank == 0) {
        std::cout << "MPI ranks=" << size
                  << "  Allreduce=" << (mpi_ok ? "PASS" : "FAIL")
                  << "  Compute=" << (compute_ok ? "PASS" : "FAIL")
                  << "  OMP=" << (omp_ok ? "PASS" : "FAIL")
                  << "  time=" << compute_ms << "ms" << std::endl;
    }
    std::cout << " rank=" << rank << " host=" << hostname
              << " threads=" << nthreads << " omp_sum=" << omp_sum << std::endl;

    MPI_Finalize();
    return (mpi_ok && compute_ok && omp_ok) ? 0 : 1;
}
```

### Build all three variants

```sh
# Fujitsu
/opt/FJSVxtclanga/tcsds-1.2.43/bin/mpiFCCpx -Kfast -Kopenmp verify.cpp -o verify_fujitsu -lpthread

# GCC cross
source /vol0004/apps/oss/gcc-arm-11.2.1/setup-env.sh
/opt/FJSVxtclanga/tcsds-1.2.43/bin/mpiFCCpx -O3 -fopenmp verify.cpp -o verify_gcc -lpthread

# LLVM
module load LLVM/llvmorg-22.1.0
/vol0004/apps/r/OSS_CN/llvm-22.1.0/fj-mpi/cross_mpi/bin/mpiclang++ \
  -O3 -fopenmp verify.cpp -o verify_llvm -lpthread
```

### Submit a validation job

Use at least 2 nodes to prove MPI isn't silently collapsing to localhost:

```sh
#PJM -L rscgrp=f-pt
#PJM -L node=4
#PJM --mpi proc=4
#PJM -L elapse=00:15:00
#PJM -g ra000009
```

```sh
export OMP_NUM_THREADS=12

for binary in verify_fujitsu verify_gcc verify_llvm; do
  # LLVM OpenMP runtime needs its library path
  if [[ "${binary}" == verify_llvm ]]; then
    export LD_LIBRARY_PATH="/vol0004/apps/r/OSS_CN/llvm-22.1.0/cross_clangfx/lib64:\
${LD_LIBRARY_PATH:-}"
  else
    unset LD_LIBRARY_PATH
  fi

  mpiexec -n 4 "./${binary}"
done
```

### Expected output

Look for:
- **Multiple hosts** in the `host=` lines (not all the same hostname)
- **Allreduce=PASS** (proves MPI collectives work across ranks)
- **OMP=PASS** with `threads=12` (proves OpenMP is active)
- **Compute time** should be ~5–15 ms for the 256×256 kernel with `-Kfast` or `-O3`; significantly slower with `-O0`

---

## Job-submission tips

### Priority queue: `f-pt`

Fugaku provides a point-based priority resource group `f-pt`. It consumes Fugaku Points from the project group and bypasses the normal `small` queue backlog.

Check point balance:

```sh
accountj_pt
```

Submit exactly like `small` but with `rscgrp=f-pt`:

```sh
#PJM -L "rscgrp=f-pt"
#PJM -L "node=1"
#PJM -L "elapse=00:20:00"
```

Same node/elapse limits as `small` (node=1..12288, elapse=00:01:00..24:00:00).

### `pjsub` CWD restriction

`pjsub` refuses to submit if the current working directory is not inside a data area. Either `cd` into the job script directory or use `--no-check-directory`:

```sh
cd /home/ra000009/data/u10035/myjob && pjsub job.sh
# or
pjsub --no-check-directory /home/ra000009/data/u10035/myjob/job.sh
```

### Interactive resource group

For very short debug sessions, `rscgrp=int` has a 1-hour default elapse limit and supports `pjsub --interact`.

---

## Runtime gotchas

### LLIO localtmp staging

If your job requests LLIO (`PJM_LLIO_GFSCACHE` and `--llio localtmp-size=...`), data files are copied to compute-node localtmp at start and written back at end. **Output files may not appear in Lustre until the job finishes.** Do not assume a running job has no output just because the directory looks empty.

### Spack OpenBLAS runtime path

If you link against Spack OpenBLAS (`.so`), add its directory to `LD_LIBRARY_PATH`:

```sh
export LD_LIBRARY_PATH="/vol0004/apps/oss/spack-v1.0.1/opt/spack/linux-a64fx/\
openblas-0.3.30-tayl3edqrmltxa7fylvolkjwg4rvj3gg/lib:${LD_LIBRARY_PATH}"
```

### GCC cross runtime LD_LIBRARY_PATH gotcha

After GCC cross activation, the setup script adds the GCC cross `lib64` directory to `LD_LIBRARY_PATH`. **Do not propagate this to compute-node job scripts.** The GCC cross `libgcc_s.so.1` can require a newer glibc than what Fugaku compute nodes provide, causing `mpiexec` itself to fail at startup with:

```
mpiexec: /lib64/libc.so.6: version 'GLIBC_2.34' not found
(required by /vol0004/apps/oss/gcc-arm-11.2.1/aarch64-linux-gnu/lib64/libgcc_s.so.1)
```

**Fix:** In your job script, set `LD_LIBRARY_PATH` to only what the *binary* needs at runtime (e.g., Spack OpenBLAS), and do **not** prepend the GCC cross `lib64`:

```sh
# GOOD — only add what the application binary needs
export LD_LIBRARY_PATH="/vol0004/apps/oss/spack-v1.0.1/opt/spack/linux-a64fx/\
openblas-0.3.30-tayl3edqrmltxa7fylvolkjwg4rvj3gg/lib:${LD_LIBRARY_PATH:-}"

# BAD — this poisons mpiexec
export LD_LIBRARY_PATH="/vol0004/apps/oss/gcc-arm-11.2.1/aarch64-linux-gnu/lib64:${LD_LIBRARY_PATH}"
```

The GCC cross compiler's own `libgcc_s`/`libstdc++` are typically compatible with the compute-node system libraries — the binary's ELF `RPATH`/`RUNPATH` or default search order picks them up automatically. Explicitly overriding with the GCC cross `lib64` is what breaks `mpiexec`.

### Fortran preprocessor directives (`#ifdef`)

Fujitsu `mpifrtpx` does **not** preprocess Fortran source by default. If your code uses C preprocessor directives inside `.f90` files (e.g., `#ifdef SIRIUS` / `#else` / `#endif` blocks, common in legacy Fortran codes like ELK), compilation fails with syntax errors on the `#` lines.

**Fix:** Add the `-Cpp` flag to both `F90_OPTS` and `F77_OPTS`:

```sh
mpifrtpx -Kfast -Kopenmp -Cpp source.f90 -o object.o
```

Alternatively, use the `.F90` extension (capital F), which many compilers including Fujitsu treat as "preprocess this file."

### Fujitsu MPI stdout paths

Fujitsu MPI places per-rank stdout in:

```
output.<JOBID>/0/1/stdout.1.0
```

Plan log-gathering scripts accordingly.

---

## Build diagnostics checklist

1. `mpicxx -show` — confirm the real compiler being invoked.
2. `nm libblas.so | grep dsyev_` — confirm the BLAS library exports the expected mangled symbol.
3. If GCC/Clang configuration succeeds but link fails with `undefined reference to 'dsyev_'` — you are hitting the SSL2 Fortran name-mangling mismatch. Switch to Spack OpenBLAS.
4. If a linked executable fails at runtime with `error while loading shared libraries: libomp.so` — add the LLVM OpenMP runtime directory to `LD_LIBRARY_PATH`.
5. If `mpiexec` fails at startup with a glibc version mismatch on a GCC-cross binary — remove the GCC cross `lib64` from your job script's `LD_LIBRARY_PATH`.
6. If Fortran compilation fails with "Not a valid Fortran statement" on lines containing `#ifdef` — add `-Cpp` to compiler flags (or use `.F90` extension).
7. If `pjsub` refuses to submit after a successful build, check the CWD and use `--no-check-directory`.
8. If a binary seems to run but only one hostname appears in output — MPI may have silently collapsed to localhost. Verify with `mpiexec -n <N>` on multiple nodes.
9. Keep CPU and GPU build directories separate; stale CMake flags can silently leak between builds.

Base directory for this skill: /Users/wddawson/Documents/FugakuNEXT/fugaku-sbd/.claude/skills/fugaku-build
