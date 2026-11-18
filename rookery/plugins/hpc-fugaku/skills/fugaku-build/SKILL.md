---
name: fugaku-build
description: Use when building, compiling, linking or profiling software on Fugaku — choosing a compiler toolchain (Fujitsu vs LLVM vs GCC), MPI, BLAS/LAPACK, cross-compilation for A64FX, verifying a build actually produces working parallel code, and measuring where time goes (fipp, fapp, perf, percent of peak).
user-invocable: true
---

# Building software on Fugaku

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

### Be skeptical of any Fujitsu build not using `-Kfast`

A Fujitsu-compiler build at `-O2` (or with no level at all) should be
treated as unoptimised until shown otherwise. `-O2` is a common "safe"
choice while a cross-build is still being debugged, and it then tends to
stay in the recipe. When you inherit a build, read its actual compile line
(`config.log`, the build log, `make VERBOSE=1`) before trusting its
timings. Comparing such a build against GCC `-O3` or LLVM `-O3` compares
optimisation levels, not compilers.

Without `-Kfast`, frt keeps strict IEEE semantics. Floating-point division
and `SQRT` then use the full-precision hardware instructions instead of
reciprocal-estimate sequences, and complex division, `ABS` and `**` go
through careful runtime routines (e.g. `__g_cdabs`). In arithmetic-heavy
loops that can cost a large factor.

`-Kfast` relaxes those semantics (reciprocal approximations, FMA
contraction, flush-to-zero). Build a strict (`-O2`) and a `-Kfast` binary
of the same source, and **compare their science output** before adopting
the faster one.

### Optimization control lines (OCL)

Fujitsu Fortran accepts per-loop and per-routine optimisation directives,
so you can relax or tune only the code that matters and leave the rest of
the build strict (or the reverse). Fortran syntax is `!OCL <specifier>`
placed immediately before a program unit, a `DO` loop, or an array
assignment statement:

```fortran
!OCL FP_RELAXED
DO I = 1, N
   A(I) = SQRT(B(I) / C(I))
END DO
```

- `FP_RELAXED` converts division and `SQRT` in that scope to
  reciprocal-approximation + FMA sequences, the same as `-Kfp_relaxed`. It
  may add rounding error relative to IEEE and can raise unexpected
  floating-point exceptions under `-NRtrap`.
- OCL lines are honoured only with `-Kocl` and at `-O1` or higher.
  **`frtpx` defaults to `-Knoocl`**, so without `-Kocl` every `!OCL` line is
  silently ignored: no warning, and the generated code does not change (the
  man page and the Fortran User's Guide, OCL chapter, both say so). Check
  that a directive took effect with `-S` or the `-Nlst=t` listing.
- In C/C++ **trad mode** the equivalents are pragmas with an explicit
  scope: `#pragma procedure fp_relaxed` inside a function, `#pragma loop
  fp_relaxed` before a loop, or `global`. **Clang mode (`-Nclang`) has no
  per-loop form**; use the global option `-ffj-fp-relaxed`.
- Other specifiers (SIMD, unrolling, recurrence hints and more) are listed
  in the Fujitsu Fortran/C user's guides. Check the manual for the exact
  spelling rather than guessing.

To see what the compiler actually did with a loop, add
`-Koptmsg=2 -Nlst=t`. frt then writes a listing that explains which loops
were vectorised (SVE), unrolled or software-pipelined, and why not. If a
hot loop still runs scalar after `-Kfast`, the listing tells you whether a
directive or a source change is needed.

### `-Kfast` numerical hazards (seen in a production code)

These came out of validating Yambo (GW/BSE, Fortran) at `-Kfast` against
`-O2` and GCC builds. Each one gave plausible-looking but wrong results.

- **`fp_relaxed` turns `1/Inf` into NaN.** Relaxed division is a reciprocal
  estimate plus Newton steps, and that sequence gives NaN for an infinite
  divisor where IEEE gives 0. Code that lets `exp` overflow on purpose, such
  as Fermi/Bose factors `1/(1+exp(x))` or `1/(exp(x)-1)`, then produces NaN.
  We saw an all-NaN finite-temperature result, and "Not enough states to
  converge the Fermi Level" for a metal. Fix it in the source: cap the
  argument (`exp(min(x,80._SP))`). That is also correct under IEEE.
- **Small, systematic shifts.** Relaxed arithmetic in one module that
  converts k/q/G vectors between units (divisions by the lattice constant,
  a `sqrt` for the norm) shifted the quasiparticle energies of a metal by
  0.2 meV. `-O2` and GCC agreed with each other to 1e-6 eV. Nothing crashed,
  and the semiconductor tests matched exactly.
- **Turning it off for one unit needs two OCL specifiers.** `!OCL
  NOFP_RELAXED` alone restored the exact divisions but left the FMA
  contractions, and the shift remained. This fixed it with no measurable
  cost, compiled with `-Kocl`:

  ```fortran
  !OCL NOFP_RELAXED,NOFP_CONTRACT
  module vec_operate
  ```

  An OCL line placed before a `module` statement covers the whole module.
  Comment lines survive a `-Cpp` preprocessing step; check the preprocessed
  file if the build has its own cpp stage.
- **Find the unit by relinking, not by rebuilding.** Recompile one source
  directory (then one file) at `-O2` against the `-Kfast` build's own module
  files, relink into a separate `bin`, and run one large job per variant.
  To narrow the field before spending a job, compare the `-S` output of
  the two flag sets: counts of `fdiv`/`fsqrt` versus `frecpe`/`frsqrte`,
  and of `fmadd`/`fmsub`. Only files whose counts change are candidates.
- **`-Ksimd=2` on a whole build can crash** (SIGSEGV). It vectorises loops
  with IFs by executing both branches, so a guarded gather such as
  `if (ig > n) cycle; x = table(ig)` reads past the end of `table`. That is
  documented `-Ksimd=2` behaviour, not a bug in the code. Use it per file,
  only where speculation is safe. `!OCL SIMD` does **not** request the same
  IF-conversion: a loop rejected with "there are IF statements in the loop"
  stays scalar.
- **`collapse(2)` can block vectorisation.** frt rebuilds both indices of a
  collapsed OpenMP loop with an SVE integer divide for every element. In
  one hot loop that took about 40% of the time. Dropping `collapse(2)` and
  parallelising only the outer loop let the inner one vectorise and be
  software pipelined. The whole region ran about 4× faster, with no
  load-balance penalty even at about 2 outer iterations per thread.
  `-Kopenmp_collapse_except_innermost` did not combine with `-Ksimd=2`.
- Option spelling: `-Ksimd_nopacked_promotion` (not
  `-Knosimd_packed_promotion`, which only gives a warning and is ignored).

### Run-time checking builds (`-H`)

`-Haefosu` (argument, shape, bounds, overlap, undefined values; implies
`-O0`) objects can be linked with normally optimised objects. **`-Hx` cannot
be mixed:** it changes the module data layout, so every unit that uses a
`-Hx`-compiled module must also be `-Hx`. A mixed link built fine and then
failed with "undefined" checks on correctly set components and a SIGSEGV in
`MPI_Comm_size`. Whole-program `-H` builds of a large code can be too slow to
reach the code you care about; recompiling only the suspect directories at
`-O0 -Haefosu` against the optimised build's modules works.

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

### Native Spack GCC builds must run in a batch job

The site's Spack GCCs (e.g. `gcc@12.2.0`, plus the Fujitsu-MPI wrappers
for GCC under `/vol0004/apps/oss/mpigcc/fjmpi-gcc{8,10,11,12}`) are
**A64FX-native**, not cross compilers. This is the one case where the
"don't build on compute nodes" advice above does not apply. A `spack install`
of a GCC + Fujitsu-MPI stack has to run inside a `pjsub` job:

- `arm1` (the Arm login node) is **not** a substitute. It runs glibc 2.17, so
  the RHEL 8-built GCC fails with `GLIBC_2.25 not found`. It also has no
  internet access, and the site's Fujitsu-built Spack Python fails there.
- Concretize and `spack fetch` on an **x86 login node** (it has internet;
  set `concretizer:targets:host_compatible:false` and require
  `target=a64fx`). Then run `spack install` in an `f-pt`/`small` job.
- Inside the job set `TMPDIR=/tmp` and put the Spack build stage there.
  `$PJM_LOCALTMP` has zero capacity by default (see the
  `fugaku-submitting-jobs` storage notes), and `config.guess` fails with
  "No space left on device". Compute-node `/tmp` is per-node-group NFS and
  survives the job, so remove your stage directory **in the same job**.
- Keep stages and caches off the group data volume (see the inode note in
  `fugaku-submitting-jobs`). Unpacking sources there can fail with "Disk
  quota exceeded".
- Re-concretize after editing any recipe: Spack hashes include the
  `package.py` content.
- Give `spack install` a generous elapse limit. Configure-heavy packages
  are slow on compute nodes, and their timing varies a lot between runs.

### libgomp needs `OMP_WAIT_POLICY=active` for fine-grained OpenMP

GCC-built OpenMP codes with many short parallel regions can run several
times slower than expected under libgomp's default passive wait, because
idle threads sleep between regions. Set `OMP_WAIT_POLICY=active` in every
job running a GCC/libgomp binary before comparing it with a Fujitsu build.
Thread binding (`OMP_PROC_BIND`/`OMP_PLACES`) does not substitute for it.
The Fujitsu OpenMP runtime already spins by default.

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

### SSL2 BLAS results depend on the data address

SSL2 `zdotc` is accurate, but not bitwise reproducible: the same vectors at a
different memory alignment gave a result differing in the last bits in
about 80% of cases (same address: always identical; any thread count). Code
that repeats a computation on several ranks and assumes they agree
bitwise can drift apart, and an iterative method (Lanczos/Haydock) amplifies
it into a wrong answer that changes from run to run and with the rank count.
Symptom: runs on one MPI rank are correct and runs on several ranks are
wrong, with OpenMP on or off, while OpenBLAS builds are fine. Fix: compute
on one rank and broadcast the result, or reduce it, so all ranks use
identical values.

### Fujitsu FFTW

The site Spack has `fujitsu-fftw` 1.1.0 (A64FX-tuned FFTW3 API, `+openmp
+mpi`, Fujitsu compiler and MPI). It is a drop-in replacement for
`fftw@3.3.10` at link time. Relinking one code against it made the FFT-heavy
phase 23% faster, with identical results.

### RPATH beats `LD_LIBRARY_PATH`

A binary linked with `-rpath` (as Spack and most build systems do) keeps
loading the libraries from its RPATH even if `LD_LIBRARY_PATH` lists another
version first. Swapping in a different MPI or BLAS runtime therefore needs a
relink; check with `ldd` inside the job (on a compute node: `ldd` of a cross
binary fails on the login node).

### OpenMP stack size for native `mpifrt` programs

A small Fortran MPI+OpenMP test built with native `mpifrt -Kopenmp`
segfaulted at 12 threads with the default stack, and with `OMP_STACKSIZE=64M`.
`OMP_STACKSIZE=1G` fixed it. How much is needed depends on what the OpenMP
regions put on the thread stacks (automatic arrays, private copies), so try
a larger value when a threaded run crashes and a 1-thread run does not.

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

## Profiling

Fujitsu's tools come with TCS. Measurement happens on a compute node with
`fipp`/`fapp`; post-processing happens on the x86 login nodes with
`fipppx`/`fapppx`. **The native commands do not exist on the login node at
all** — verified on toolchain 1.2.43, where `/opt/FJSVxtclanga/tcsds-1.2.43/
bin/` carries only `fipppx` and `fapppx`. A login-node measurement attempt
therefore dies with a bare `command not found`, which is the usual reason a
profiling attempt fails instantly. (`fipp`/`fapp` can also format their own
output on a compute node with `-A` in place of `-C`; the two are mutually
exclusive.)

Pick by question:

| Question | Tool | Needs source changes? |
|---|---|---|
| Where does the whole program spend time? | `fipp` (sampling) | No |
| FLOP/s, memory bandwidth, SIMD rate, IPC, MPI cost of one region | `fapp` | Yes: mark regions |
| Full hardware breakdown (cache, pipeline, FP) as charts | `fapp` + CPU Performance Analysis Report | Yes |
| Instruction-level hot spots (`perf annotate`) | `perf` | No |

### Whole-program profile: `fipp`

Low overhead, no recompilation. Collect in the job, then format on the login
node:

```sh
fipp -C -Icpupa,mpi,call -d ./fipp_data ./app        # compute node
fipp -C -Icpupa,mpi,call -d ./fipp_data mpiexec -n 4 ./app   # MPI: wrap the launch
fipppx -A -Icall,cpupa,mpi,src -ttext -o fipp.txt -d ./fipp_data   # login node
```

- **For MPI programs, wrap the whole launch** as above. Putting `fipp`
  inside it (`mpiexec -n 4 fipp -C … ./app`) ends with "fipp: profiling
  data is invalid". Tested on a 4-rank Fortran program.
- If MPI is initialised from a C `main` (`MPI_Init` in C), link with
  `-lfjprofmpi`. Without it the profile still works but reports
  "Type of program: SERIAL" and has no MPI data.
- The report header gives the CPU clock the job ran at; use it for percent
  of peak (below).
- Set `FLIB_FASTOMP` to a true value, or `fipp` does not behave correctly.
- `-d` must name a new or empty directory, so version the name rather than
  reusing it. Give it an absolute path if the program changes its own
  working directory while running.
- Sampling needs roughly a second of runtime as a floor; below that `fipp`
  cannot measure at all.
- Builds with link-time optimisation (`-Klto`/`-flto`) lose call-graph and
  per-line accuracy; profile without it.
- At scale, restrict post-processing to a few ranks with `-p` (e.g.
  `-p0,1`) and add `-Inompi` if MPI data is not needed.
- Samples shown as `__?unknown` did not map to a procedure; change the
  sampling interval (`fipp -C -i …`).

**The interval you ask for is not the interval you get**, which is why
nudging `-i` by a little often changes nothing. Sampling is pinned to the OS
timer interrupt — roughly 11–14 ms depending on noise suppression — and the
request is rounded to a multiple of it. At a 14 ms tick, both `-i 10` and
`-i 25` give 14 ms, and `-i 100` gives 98 ms. Move it in multiples of the
tick, or not at all. Defaults and ranges: `-i` 100 ms (10–3600000), `-l` 0
meaning every procedure (0–2147483647), `-m` 3000 KB of per-thread work
buffer (1–2147483).

If a run ends with this, that buffer was too small — raise `-m` to at least
the figure it names and measure again:

```
fipp: work memory overflowed. specify memsize or more to -m option and retry.
```

### Region counters and FLOP rates: `fapp`

**`fapp` only measures code between `fapp_start`/`fapp_stop` calls**, so
the source must be instrumented and recompiled (the profiler library is
linked by default; `-Nnofjprof` / `-ffj-no-fjprof` would remove it):

```fortran
call fapp_start("solver", 1, 0)   ! name (letters, digits, _), id, level
! ... region ...
call fapp_stop("solver", 1, 0)
```

C/C++ use the same calls via `#include "fj_tool/fapp.h"`. Regions whose
level exceeds the run-time level (`-L`) are skipped, which keeps overhead
down. Then:

```sh
fapp -C -Icpupa,mpi -Hevent=pa1 -d ./fapp_pa1 ./app    # compute node
fapppx -A -Icpupa,mpi -ttext -o fapp_pa1.txt -d ./fapp_pa1   # login node
```

Event set `pa1` (or `statistics`) gives the headline numbers: FLOP/s,
memory throughput, SIMD instruction rate and IPC. To get **percent of
peak**, divide FLOP/s by the A64FX peak: 48 cores × 32 double-precision
flop/cycle × clock: 3.07 TFLOP/s per node at 2.0 GHz, 3.38 at 2.2 GHz.
The clock is not fixed: `fipp` reported 2200 MHz in `f-pt` jobs, so read it
from the profile header rather than assuming 2.0 GHz. Never pass
`-Inocpupa` at collection: it disables `-Hevent`.

**Bind threads to cores one-to-one before trusting counter data.** An
unbound run still produces numbers, but they cannot be attributed. For a
non-threaded MPI program use a VCOORD file with `core=1` for every process;
for a program that is neither threaded nor MPI, `taskset` or `numactl`.

Running `fapp -C` on a large un-instrumented MPI code (Yambo) ended with
"fapp: The profiling data is not correctly generated" and wrote no data.
Do not read that as "fapp needs regions": `fipp` gave the same message on
every Yambo executable, even for `yambo -h` and for GCC and stripped
builds, while it worked on small Fortran and C-`main` MPI programs. Fujitsu
documents the message as "the file format of the executable file is
incorrect", or more generally "the program did not end normally". The cause
for that code was never found. If `fipp` also fails on a program, the
problem is the program and `perf` is the fallback; for a whole-program
profile of a normal program, use `fipp`.

### CPU Performance Analysis Report

For the full hardware picture, run the same instrumented program several
times, one event set per run, each into its own directory: `pa1` alone for
the single-page report, `pa1`–`pa5` for the brief one, `pa1`–`pa11` for the
standard one, up to `pa1`–`pa17` for the detailed one. **That is 1, 5, 11 or
17 executions of the same program** — on Fugaku, billed node-hours each, so
say which tier is intended before promising a report.

Export each with `fapppx -A -tcsv -d ./rep<N> -o rep<N>.csv` and load the
CSVs into Fujitsu's `cpu_pa_report.xlsm` Excel macro on a desktop. At large
rank counts, limit the export with `-p` or the CSV may exceed Excel's row
limit.

Practical notes on that last step:

- The workbook lives on the login node, confirmed present at
  `/opt/FJSVxtclanga/tcsds-1.2.43/misc/cpupa/cpu_pa_report.xlsm`.
- It reads **only** files named `pa1.csv` through `pa17.csv`, from its own
  directory, and picks the tier from which ones it finds — so a missing
  `pa7.csv` quietly demotes a standard report. Name the exports to match.
- It is macro-driven, so macros must be enabled. Fujitsu records verifying
  it on Windows 11 with 64-bit Excel for Microsoft 365, and on macOS
  Catalina.
- **Do not save the workbook after it reads data**; a saved copy will not
  read a fresh set. Keep a pristine copy and work from duplicates.
- It does not support dynamically spawned processes.

### `perf` (sampling and annotation)

`perf` works inside jobs (`perf_event_paranoid` is 1), but **the hardware
`cycles` event records no samples** on these nodes: the run looks fine and
`perf report` is empty. Use the software clock event:

```sh
perf record -q -e cpu-clock -F 199 -o "perf.${OMPI_COMM_WORLD_RANK:-0}.data" -- ./app
```

Wrap the application, not `mpiexec`: put that line in a small per-rank
script and launch it with `mpiexec -n N ./wrapper.sh ./app`. A low sampling
rate like 199 Hz keeps the overhead small. Run `perf report --stdio
--sort dso,symbol` and `perf annotate --stdio -s <symbol>` **inside the job**,
where the binary and its libraries are visible. `kptr_restrict` warnings
are harmless. frt OpenMP regions show up as `<routine>._OMP_<n>_`, and
libgomp ones as `<routine>_._omp_fn.<n>`.

### Where these profiling facts come from

The `perf` behaviour, the `fapp`/`fipp` failure on Yambo, the `fipp` MPI
placement, the `-lfjprofmpi` effect and the clock come from profiling
sessions on Fugaku. The command locations and
the workbook path were checked live against toolchain 1.2.43. The flag
semantics, option ranges, event-set numbering and the conditions below are
recorded from Fujitsu's Profiler User's Guide for Technical Computing Suite
V4.0L20 (J2UL-2568-01ENZ0, September 2025) without being individually
exercised — reliable for what a flag means, worth confirming the first time a
behavioural claim matters. Ranges and event numbering can move between TCS
releases.

### Conditions that quietly invalidate a measurement

Check these before blaming the tool. Most produce no error at all — just
data that is wrong, or absent.

**Job shape.** A node-sharing job may measure incorrectly or not at all; for
MPI under node sharing the measurement fails and takes the program with it.
Profile in a job with whole nodes.

**How it was built.** Position-independent executables (`-fpie`, `-fPIE`)
cannot be measured correctly. C and C++ need `-O1` or higher for `fipp`. Do
not `strip` the executable, nor any shared library whose cost you want
attributed. If you set `-rpath` or `LD_RUN_PATH`, keep the toolchain's own
`lib64` out of `DT_RPATH` — `readelf -d` shows it, and its presence breaks
`fipp` measurement.

**What the program does.** Spawning processes via `fork`, `vfork`, `popen`
or `system` prevents correct measurement. The profilers hook MPI calls, so
they cannot coexist with the MPI profiling interface: a program using it
reports as non-MPI and `fipp` collapses every rank to `Process0`.

**Environment.** `LD_PRELOAD` breaks both tools; leave it unset. Variables
beginning `FIPP_`, `FAPP_`, `PROF_`, `FJPROF_` or `FPROF_` belong to the
profilers — do not set them. If you pass `mpiexec -x LD_LIBRARY_PATH=…`,
the profiler's own library directory has to come first in that value or the
hooks never load.

**Thread model.** Only Fujitsu automatic parallelisation and OpenMP are
measured. Raw pthreads are invisible, so a pthread-parallel code looks
single-threaded.

**Mixed-language MPI.** Linking Fortran with C/C++ needs an extra library:
`-lfjprofmpif` when linking with `mpifccpx` or `mpiFCCpx`, `-lfjprofmpi`
with `mpifrtpx`.

**Exit status.** Under a profiler the reported exit status may be the
profiler's rather than the program's — do not use it to judge whether the
application itself succeeded.

When reporting profiling results, say which tool produced them, the
*effective* sampling interval rather than the requested one, and whether
threads were bound. If a run hit any condition above, say so instead of
presenting the output as clean.

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
10. If a Fortran program with a C `main` fails to link under `mpifrtpx` — add `-mlcmain=main` to the **final link only**, not to every compile/configure test.
