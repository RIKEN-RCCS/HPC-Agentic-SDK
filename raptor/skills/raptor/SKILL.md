---
name: raptor
description: Guide for using RAPTOR to profile and alter floating-point precision in C, C++, and Fortran code. Use when working with RAPTOR, numerical precision profiling, mixed-precision analysis, or floating-point truncation in scientific code.
user-invocable: true
---

# RAPTOR — Practical Numerical Profiling of Scientific Applications

RAPTOR (from RIKEN-RCCS) is an LLVM-based tool that transparently replaces high-precision floating-point operations with lower-precision alternatives in C, C++, and Fortran code. It enables scientists to profile numerical requirements and identify precision-sensitive code regions without manual refactoring.

**Repository:** https://github.com/RIKEN-RCCS/RAPTOR

---

## Usage

### Option 1: Compiler Shims (Recommended)

RAPTOR provides drop-in compiler wrappers that automatically inject the required flags:

| Wrapper            | Replaces  |
|--------------------|-----------|
| `raptor-clang`     | `clang`   |
| `raptor-clang++`   | `clang++` |
| `raptor-flang`     | `flang`   |

Simply replace your compiler invocation, e.g.:

```bash
raptor-clang++ -O2 -o myapp myapp.cpp
```

### Option 2: Manual Flags

**Compilation** (requires at least `-O1`):

```bash
clang++ -O2 -fpass-plugin=$RAPTOR_INSTALL_DIR/lib/LLVMRaptor-$LLVM_VER.so -c myapp.cpp
```

**Linking:**

```bash
clang++ -o myapp myapp.o -lRaptor-RT-$LLVM_VER -lmpfr -lstdc++
```

**Verbose remarks** (see what RAPTOR transforms):

```bash
clang++ -O2 -Rpass=raptor -fpass-plugin=... -c myapp.cpp
```

### LTO (Whole-Program Analysis)

For deeper cross-module analysis, enable LTO:

**Compilation:**

```bash
clang++ -O2 -flto=full -fpass-plugin=$RAPTOR_INSTALL_DIR/lib/LLVMRaptor-$LLVM_VER.so -c myapp.cpp
```

**Linking (via clang/flang):**

```bash
clang++ -fuse-ld=lld -Wl,--load-pass-plugin=$RAPTOR_INSTALL_DIR/lib/LLDRaptor-$LLVM_VER.so -o myapp myapp.o -lRaptor-RT-$LLVM_VER -lmpfr -lstdc++
```

**Linking (via lld directly):**

```bash
ld.lld --load-pass-plugin=$RAPTOR_INSTALL_DIR/lib/LLDRaptor-$LLVM_VER.so ...
```

---

## API: Precision Truncation

RAPTOR provides an API to explicitly request precision truncation on specific functions.

### C/C++

Declare the truncation helper:

```cpp
template <typename fty>
fty *__raptor_truncate_op_func(fty *, int from_type, int to_type, int to_exponent, int to_mantissa);

template <typename fty>
fty *__raptor_truncate_op_func(fty *, int from_type, int to_type, int to_width);
```

**Parameters:**
- `fty *` — pointer to the function to truncate
- `from_type` — source precision in bits (e.g., 32, 64)
- `to_type` — target type: `1` = MPFR (custom precision), `0` = IEEE builtin
- `to_exponent` — exponent bits (MPFR mode)
- `to_mantissa` — mantissa bits (MPFR mode)
- `to_width` — target IEEE width in bits (IEEE mode)

**Example — truncate to custom MPFR precision (5-bit exponent, 8-bit mantissa):**

```cpp
auto f = __raptor_truncate_op_func(
    foo,   // function pointer
    32,    // from: 32-bit float
    1,     // to: MPFR custom
    5,     // exponent bits
    8);    // mantissa bits
f(a, b);
```

**Example — truncate from 64-bit to 32-bit IEEE:**

```cpp
auto f = __raptor_truncate_op_func(foo, 64, 0, 32);
f(a, b);
```

### Fortran

```fortran
interface
  function f__raptor_truncate_op_func(tfunc, from_ieee, to_type, &
      to_exponent, to_significand) result(fty) bind(c)
    use iso_c_binding
    implicit none
    integer(c_int), intent(in), value :: from_ieee, to_type, &
      to_exponent, to_significand
    type(c_funptr), intent(in), value :: tfunc
    type(c_funptr) :: fty
  end function f__raptor_truncate_op_func
end interface
```

**Example:**

```fortran
cfty = c_funloc(simple_sum)
cfty = f__raptor_truncate_op_func(cfty, 64, 1, 10, 4)
call c_f_procpointer(cfty, ffty)
c = ffty(a, b)
```

See `test/Integration/Truncate/Fortran/simple.f90` in the repo for a complete working example.

---

## Known Gotchas

### Truncation parameters must be compile-time constants

**All arguments to `__raptor_truncate_op_func` must be integer literals**, not variables. RAPTOR resolves them at compile time via the LLVM pass. Passing a runtime variable causes a compiler crash:

```
Assertion `isa<To>(Val) && "cast<Ty>() argument of incompatible type!"' failed.
Running pass "RaptorNewPM" on module ...
```

To sweep multiple precisions, use a macro to stamp out separate calls per constant:

```cpp
#define RUN_TRUNC(MBITS) do { \
    auto fn = __raptor_truncate_op_func(my_func, 64, 1, 11, MBITS); \
    /* ... use fn ... */ \
} while(0)

RUN_TRUNC(8);
RUN_TRUNC(16);
RUN_TRUNC(23);
RUN_TRUNC(52);
#undef RUN_TRUNC
```

### Runtime library is static, not shared

The RAPTOR runtime is typically installed as a static archive (`libRaptor-RT-<VER>.a`), not a `.so`. The `-lRaptor-RT-<VER>` flag may not resolve. Link explicitly by path instead:

```makefile
# Instead of: -lRaptor-RT-$(LLVM_VER)
RLIBS = -L$(RAPTOR_INSTALL_DIR)/lib $(RAPTOR_INSTALL_DIR)/lib/libRaptor-RT-$(LLVM_VER).a -lmpfr -lstdc++
```

### Guard RAPTOR API calls with a preprocessor macro

The `__raptor_truncate_op_func` symbol is only available when linking against the RAPTOR runtime. A plain build (without RAPTOR flags) will fail to link. Use a preprocessor guard so the same source file compiles both ways:

```cpp
#ifdef USE_RAPTOR
template <typename fty>
fty *__raptor_truncate_op_func(fty *, int from_type, int to_type, int to_exponent, int to_mantissa);
template <typename fty>
fty *__raptor_truncate_op_func(fty *, int from_type, int to_type, int to_width);
#endif

// ...

#ifdef USE_RAPTOR
    auto f = __raptor_truncate_op_func(my_func, 64, 0, 32);
    // reduced precision experiment ...
#endif
```

In the Makefile, pass `-DUSE_RAPTOR` only for the instrumented target:

```makefile
solver:        solver.cpp
    $(CXX) $(CXXFLAGS) -o $@ $<

solver_raptor: solver.cpp
    $(CXX) $(CXXFLAGS) $(RFLAGS) -DUSE_RAPTOR -o $@ $< $(RLIBS)
```

### Functions to truncate must be passed as function pointers

The truncation API wraps a specific function. To use it, your calling code must accept a function pointer rather than calling the target directly:

```cpp
// Refactor callers to accept a function pointer
double rk4_step(double t, double y, double h,
                double (*deriv_fn)(double, double)) { ... }

// Then swap in the truncated version
auto deriv_f32 = __raptor_truncate_op_func(deriv, 64, 0, 32);
rk4_step(t, y, h, deriv_f32);
```

---

## Precision Quick Reference

IEEE and MPFR-equivalent mantissa bit counts for common formats (exponent bits in parentheses):

| Format      | Exponent bits | Mantissa bits |
|-------------|---------------|---------------|
| double      | 11            | 52            |
| float       | 8             | 23            |
| half        | 5             | 10            |
| bfloat16    | 8             | 7             |

When using MPFR mode to emulate a target format, match the exponent to the format above and vary the mantissa to find the minimum sufficient precision for your application.
