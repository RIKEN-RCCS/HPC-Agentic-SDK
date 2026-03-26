---
name: openacc
description: Template-based skill for automatically inserting OpenACC directives into Fortran code. Uses a verified pattern library to achieve reliable GPU parallelization.
user-invocable: true
---

# OpenACC Directive Insertion Skill

## Overview

This skill automatically inserts OpenACC directives into Fortran code using a **template-based** approach. Rather than relying on LLM inference, it uses a verified pattern library extracted from real, working code examples to achieve high reliability.

## Design Philosophy

### Why Template-Based?

LLM inference-based approaches have the following drawbacks:
- Complex optimizations (e.g., wavefront parallelization) tend to fail
- Risk of compilation errors and runtime errors
- Low consistency and reproducibility of output

The template-based approach is:
- **Verified**: Extracted from code that actually works
- **Predictable**: Same pattern always produces the same template
- **Incremental**: Start from simple patterns and build up

### Target Applications

Primarily scientific computing codes such as NAS Parallel Benchmarks (NPB):
- **MG (Multi-Grid)**: Dominated by independent 3D array loops
- **CG (Conjugate Gradient)**: Reduction operations
- **LU**: Jacobian computation, norm calculation

## Pattern Library

### P1: Independent Loops

The most basic and easiest-to-apply pattern. Direct parallelization of loops with no data dependencies.

- **P1_independent_2D**: 2D loops (`collapse(2)`)
- **P1_independent_3D**: 3D loops (`collapse(3)`)
- **P1_independent_4D**: 4D loops (`collapse(4)`)

**Typical signature**:
```fortran
do j = jst, jend
  do i = ist, iend
    v(i,j,k) = v(i,j,k) + rhs(i,j,k)
  end do
end do
```

**After applying**:
```fortran
!$acc parallel loop present(v, rhs) collapse(2)
do j = jst, jend
  do i = ist, iend
    v(i,j,k) = v(i,j,k) + rhs(i,j,k)
  end do
end do
```

### P2: Reduction

Accumulation patterns used in norm and error calculations.

**Typical signature**:
```fortran
sum = 0.0d0
do k = 2, nz0-1
  do j = jst, jend
    do i = ist, iend
      sum = sum + v(i,j,k) * v(i,j,k)
    end do
  end do
end do
```

**After applying**:
```fortran
sum = 0.0d0
!$acc parallel loop collapse(3) reduction(+:sum) present(v)
do k = 2, nz0-1
  do j = jst, jend
    do i = ist, iend
      sum = sum + v(i,j,k) * v(i,j,k)
    end do
  end do
end do
```

**Important**: Initialization must be done **outside** the `!$acc` region.

### P3: Array Initialization

Pattern for initializing entire arrays. Two variants: `kernels` and `parallel loop`.

**kernels version (recommended)**:
```fortran
!$acc kernels present(a)
a = 0.0
!$acc end kernels
```

**parallel loop version (when fine-grained control is needed)**:
```fortran
!$acc parallel loop collapse(3) present(a)
do k=1,n
  do j=1,n
    do i=1,n
      a(i,j,k) = 0.0
    end do
  end do
end do
```

### P4: Data Region ⚡ **CRITICAL**

**Most important pattern**: Minimizes CPU-GPU data transfers.

**Problem**: Using `copy` clause in each kernel causes a transfer on every call.
```fortran
! Bad: 1000 transfers for 1000 iterations!
do step = 1, 1000
!$acc parallel loop copy(u, v) collapse(3)  ! <- 83ms transfer every time
  do k=1,n
    ...
  end do
end do
! Total: 83 seconds wasted
```

**Solution**: Wrap in a `data region`.
```fortran
! Good: only 2 transfers (start and end)
!$acc data copy(u, v) copyin(r)

  do step = 1, 1000
!$acc parallel loop present(u, v, r) collapse(3)  ! <- no transfer
    do k=1,n
      ...
    end do
  end do

!$acc end data
! Total: 0.17 seconds (500x speedup!)
```

**Data clause selection**:
- `copy(u, v)`: Input/output arrays (CPU→GPU→CPU)
- `copyin(r)`: Read-only arrays (CPU→GPU)
- `copyout(result)`: Write-only arrays (GPU→CPU)
- `create(temp)`: Temporary arrays (no transfer, allocated on GPU)

**Application levels**:
1. **Entire subroutine** (most effective)
2. **Entire time-step loop**
3. **Block of multiple kernels**

### P5: Structured Data

**Program-wide data management**: Explicit control via `enter data`/`exit data`.

```fortran
program main
  double precision u(n,n,n), v(n,n,n)

  call initialize(u, v, n)

  ! Transfer at initialization (once)
!$acc enter data copyin(u, v)

  ! All computation on GPU
  call compute1(u, v, n)
  call compute2(u, v, n)
  call compute3(u, v, n)

  ! Retrieve results at end (once)
!$acc exit data copyout(u, v)

end program
```

**Benefits**:
- GPU memory persists across the entire program
- Unstructured (cross-function) data management
- Maximum reduction in transfers

**Intermediate update** (debug only):
```fortran
!$acc update self(u)    ! GPU->CPU (for inspection)
print *, 'Debug: u(1) =', u(1)
!$acc update device(u)  ! CPU->GPU (apply changes)
```

### P6: Update Optimization

**Partial array transfer**: Transfer only the required portion of an array.

```fortran
! 1000x1000 array, but only 100x100 is used
!$acc data copy(u(ist:iend, jst:jend))  ! Only 80KB (1% of 8MB)

!$acc parallel loop present(u) collapse(2)
  do j = jst, jend
    do i = ist, iend
      u(i,j) = u(i,j) * 2.0
    end do
  end do

!$acc end data
```

**Effect**: Reduces transfer volume 100x → 100x speedup

## Usage

### Data Management Strategy ⚡ (Most Important)

**CPU-GPU data transfer is the biggest bottleneck.** Even fast computation won't help if transfers are slow.

#### Decision Flow

1. **Are the same arrays used across multiple kernels?**
   - YES → Use **P4 (data region)** ✅
   - NO → Use `copy` clause per kernel (but slow)

2. **Should GPU memory persist across the entire program?**
   - YES → Use **P5 (enter/exit data)** ✅
   - NO → P4 is sufficient

3. **Is only part of an array needed?**
   - YES → Use **P6 (partial array)** ✅
   - NO → Transfer the full array

#### Basic Rules

1. **Place `data region` at the largest possible scope**
   - ❌ Inside each loop
   - ✅ Entire subroutine or entire time-step loop

2. **Use only `present` clause inside kernels**
   - ❌ `!$acc parallel loop copy(u, v)`
   - ✅ `!$acc parallel loop present(u, v)`

3. **Minimize `update` directives** (debug only)

4. **Use `create` clause for temporary arrays**
   - ❌ `copy(temp)` (unnecessary transfer)
   - ✅ `create(temp)` (allocate on GPU only)

#### Typical Workflow

```fortran
subroutine my_computation(u, v, r, a, n, niter)
  integer n, niter
  double precision u(n,n,n), v(n,n,n), r(n,n,n), a(0:3)
  double precision temp(n,n,n)  ! temporary array

  ! Open data region
!$acc data copy(u, v) &      ! input/output
!$acc&     copyin(r, a) &    ! read-only
!$acc&     create(temp)      ! temporary (no transfer)

  ! Time-step loop
  do step = 1, niter

    ! Kernel 1: all present clauses
!$acc parallel loop present(u, v, r, a, temp) collapse(3)
    do k=2,n-1
      do j=2,n-1
        do i=2,n-1
          temp(i,j,k) = v(i,j,k) - a(0)*u(i,j,k)
        end do
      end do
    end do

    ! Kernel 2
!$acc parallel loop present(u, temp) collapse(3)
    do k=2,n-1
      do j=2,n-1
        do i=2,n-1
          u(i,j,k) = u(i,j,k) + 0.5*temp(i,j,k)
        end do
      end do
    end do

  end do

  ! Close data region (u, v are copied back to CPU here)
!$acc end data

end subroutine
```

### Step 1: Detect Pattern

Statically analyze the Fortran code to identify applicable patterns.

**Features to detect**:
- Loop nesting structure (2D, 3D, 4D)
- Presence or absence of data dependencies
- Array access patterns
- Accumulation operations

### Step 2: Select Pattern

Based on detected features, choose the appropriate pattern ID (P1–P6) from the pattern library below.

### Step 3: Fill Placeholders

Replace `{{...}}` placeholders in the template with actual values:

**Placeholder examples**:
- `{{ARRAYS}}`: `v, rhs, u` (array list for present clause)
- `{{J_VAR}}`: `j` (outer loop variable)
- `{{J_START}}`: `jst` (start value)
- `{{J_END}}`: `jend` (end value)
- `{{I_VAR}}`: `i` (inner loop variable)
- `{{I_START}}`: `ist` (start value)
- `{{I_END}}`: `iend` (end value)
- `{{LOOP_BODY}}`: original loop body as-is

### Step 4: Validate

Verify the generated code against the `validation_rules` in the pattern library below.

### Step 5: Compile and Run

```bash
# NVIDIA HPC SDK
nvfortran -acc -Minfo=accel -o test test.f90
./test
```

## Implementation Guidelines

### Incremental Approach

1. **Phase 1**: Apply only the simplest P1 patterns
   - Start with independent loops in MG and CG
   - Confirm successful compilation and execution

2. **Phase 2**: Add reduction patterns
   - Apply to norm and error calculations

3. **Phase 3**: Consider more complex patterns
   - Improve dependency analysis accuracy
   - Add custom patterns as needed

### Template Selection Priority

1. **Choose the best-matching pattern** based on loop nesting depth, array access patterns, and dependency characteristics
2. **Conservative approach**: If unsure, do not apply — prompt for human review
3. **Use profiling data**: Prioritize loops with the longest execution time

## Performance Notes

### Memory Access Efficiency

Fortran uses **column-major** array layout:
```fortran
! buf(i,j,k): i-direction is most contiguous
! Recommended loop order: outer k, middle j, inner i
```

### Importance of collapse Clause

```fortran
! Good: parallelizes all dimensions
!$acc parallel loop collapse(3)

! Bad: only outer loop parallelized (insufficient parallelism)
!$acc parallel loop
```

### Minimizing Data Transfer with present Clause

```fortran
! Good: data already on GPU
!$acc parallel loop present(v, rhs)

! Bad: CPU-GPU transfer on every call
!$acc parallel loop copy(v, rhs)
```

## NPB Application Examples

### MG (Multi-Grid)

Primarily 3D independent loops (P1_independent_3D):
```fortran
! resid.f, psinv.f, rprj3.f, etc.
!$acc parallel loop collapse(3) present(...)
do k = 2, n3-1
  do j = 2, n2-1
    do i = 2, n1-1
      ...
    end do
  end do
end do
```

### CG (Conjugate Gradient)

Centered on reduction operations (P2_reduction_simple):
```fortran
! norm calculation
!$acc parallel loop reduction(+:sum) present(...)
```

### LU

Combination of independent loops (Jacobian) and reduction (norm):
```fortran
! jacld.f, jacu.f: P1_independent_3D
! l2norm.f, error.f: P2_reduction_simple
```

## Troubleshooting

### Compilation Error

**Symptom**: `PGF90-S-0034-Syntax error`

**Fix**:
- Check syntax of `!$acc` directives
- Verify dimension count in `collapse(N)`
- Check array list in `present()`

### Runtime Error

**Symptom**: `call to cuStreamSynchronize returned error 700`

**Fix**:
- Check for out-of-bounds array access
- Verify data transfer (present vs copy)
- Check for dependency violations

### Performance Regression

**Symptom**: Slower than CPU

**Fix**:
- Maximize parallelism with `collapse(N)`
- Revisit data management strategy (apply P4/P5)
- Use profiler to identify bottleneck

## Limitations

### Unsupported Patterns

- **Wavefront parallelization**: Dependency chains in LU solver
- **Pipeline parallelization**: Time-direction dependencies
- **Dynamic parallelism**: Loop bounds determined at runtime

### Conservative Approach

- **Apply only patterns that are clearly safe**
- When uncertain, prompt the user for manual review
- Add comments explaining the rationale

## Verified Templates (Machine-Readable)

Canonical template definitions for each pattern. Claude uses these to select templates, fill placeholders, and validate generated code.

```json
{
  "version": "2.0",
  "source": "github.com/jeng1220/openacc_fortran_examples",
  "patterns": {
    "P1_independent_2D": {
      "template": {
        "openacc_directive": "!$acc parallel loop present({{ARRAYS}}) collapse(2)",
        "full_example": "!$acc parallel loop present(buf) collapse(2)\ndo j=1, n\n  do i=1, n\n    buf(i, j) = buf(i, j) + 1\n  end do\nend do",
        "placeholders": {
          "{{ARRAYS}}": "array list for present clause (e.g. buf, a, b)",
          "{{J_VAR}}": "outer loop variable",
          "{{J_START}}": "j start value",
          "{{J_END}}": "j end value",
          "{{I_VAR}}": "inner loop variable",
          "{{I_START}}": "i start value",
          "{{I_END}}": "i end value",
          "{{LOOP_BODY}}": "loop body (verbatim from original)"
        }
      },
      "validation_rules": [
        {"type": "required", "pattern": "!\\$acc parallel loop", "message": "OpenACC parallelization directive required"},
        {"type": "required", "pattern": "collapse\\(2\\)", "message": "collapse(2) required for 2D loop"},
        {"type": "required", "pattern": "present\\(", "message": "present clause required"}
      ]
    },
    "P1_independent_3D": {
      "template": {
        "openacc_directive": "!$acc parallel loop present({{ARRAYS}}) collapse(3)",
        "full_example": "!$acc parallel loop present(buf) collapse(3)\ndo k=1, n\n  do j=1, n\n    do i=1, n\n      buf(i, j, k) = buf(i, j, k) + 1\n    end do\n  end do\nend do",
        "placeholders": {
          "{{ARRAYS}}": "array list for present clause",
          "{{K_VAR}}": "outermost loop variable",
          "{{K_START}}": "k start value",
          "{{K_END}}": "k end value",
          "{{J_VAR}}": "middle loop variable",
          "{{J_START}}": "j start value",
          "{{J_END}}": "j end value",
          "{{I_VAR}}": "innermost loop variable",
          "{{I_START}}": "i start value",
          "{{I_END}}": "i end value",
          "{{LOOP_BODY}}": "loop body"
        }
      },
      "validation_rules": [
        {"type": "required", "pattern": "collapse\\(3\\)", "message": "collapse(3) required for 3D loop"},
        {"type": "required", "pattern": "present\\(", "message": "present clause required"}
      ]
    },
    "P1_independent_4D": {
      "template": {
        "openacc_directive": "!$acc parallel loop present({{ARRAYS}}) collapse(4)",
        "full_example": "!$acc parallel loop present(a) collapse(4)\ndo l = 1, n\n  do k = 1, n\n    do j = 1, n\n      do i = 1, n\n        a(i,j,k,l) = 0.0\n      end do\n    end do\n  end do\nend do",
        "placeholders": {
          "{{ARRAYS}}": "array list for present clause",
          "{{L_START}}": "l start", "{{L_END}}": "l end",
          "{{K_START}}": "k start", "{{K_END}}": "k end",
          "{{J_START}}": "j start", "{{J_END}}": "j end",
          "{{I_START}}": "i start", "{{I_END}}": "i end",
          "{{LOOP_BODY}}": "loop body"
        }
      },
      "validation_rules": [
        {"type": "required", "pattern": "collapse\\(4\\)", "message": "collapse(4) required for 4D loop"}
      ]
    },
    "P2_reduction_simple": {
      "template": {
        "openacc_directive": "!$acc parallel loop collapse({{COLLAPSE_N}}) reduction({{OP}}:{{VAR}}) present({{ARRAYS}})",
        "full_example": "sum = 0.0d0\n!$acc parallel loop collapse(3) reduction(+:sum) present(v)\ndo k = 2, nz0-1\n  do j = jst, jend\n    do i = ist, iend\n      sum = sum + v(i,j,k) * v(i,j,k)\n    end do\n  end do\nend do",
        "placeholders": {
          "{{COLLAPSE_N}}": "number of collapse dimensions (2 or 3)",
          "{{OP}}": "operator (+, *, max, min)",
          "{{VAR}}": "accumulation variable name",
          "{{ARRAYS}}": "array list",
          "{{LOOP_BODY}}": "loop body containing accumulation"
        },
        "critical_note": "Initialize accumulation variable outside the !$acc region. Array reduction also supported: reduction(+:sum[0:4])"
      },
      "validation_rules": [
        {"type": "required", "pattern": "reduction\\(", "message": "reduction clause required"},
        {"type": "required", "pattern": "present\\(", "message": "present clause required"}
      ]
    },
    "P3_array_initialization": {
      "template": {
        "kernels_version": {
          "directive": "!$acc kernels present({{ARRAY}})\n{{ARRAY}} = {{VALUE}}\n!$acc end kernels",
          "note": "Compiler auto-optimizes (recommended)"
        },
        "parallel_loop_version": {
          "directive": "!$acc parallel loop collapse({{N}}) present({{ARRAY}})",
          "note": "Explicit parallelization (fine-grained control)"
        }
      },
      "validation_rules": [
        {"type": "required", "pattern": "present\\(", "message": "present clause required"}
      ]
    },
    "P4_data_region": {
      "template": {
        "subroutine_level": "!$acc data copy({{COPY_INOUT}}) &\n!$acc&     copyin({{COPYIN}}) &\n!$acc&     create({{TEMPS}})\n\n  {{COMPUTATION_BODY}}\n\n!$acc end data",
        "iteration_level": "!$acc data copy({{ARRAYS}})\n\n  do {{TIME_VAR}}={{START}}, {{END}}\n    {{ITERATION_BODY}}\n  end do\n\n!$acc end data",
        "data_clauses": {
          "copy": "input/output arrays (CPU->GPU->CPU)",
          "copyin": "read-only arrays (CPU->GPU)",
          "copyout": "write-only arrays (GPU->CPU)",
          "create": "temporary arrays (no transfer, allocate on GPU)"
        },
        "rule": "kernels inside data region must use present clause"
      },
      "validation_rules": [
        {"type": "required", "pattern": "!\\$acc data", "message": "data region start required"},
        {"type": "required", "pattern": "!\\$acc end data", "message": "data region end required"},
        {"type": "consistency", "pattern": "present\\(", "message": "kernels inside data region should use present clause"}
      ]
    },
    "P5_structured_data": {
      "template": {
        "enter": "!$acc enter data copyin({{READONLY}}) &\n!$acc&            create({{WORK}})",
        "exit": "!$acc exit data copyout({{OUTPUT}}) &\n!$acc&           delete({{TEMPS}})",
        "update_device": "!$acc update device({{ARRAYS}})",
        "update_self": "!$acc update self({{ARRAYS}})"
      },
      "validation_rules": [
        {"type": "paired", "pattern": "enter data.*exit data", "message": "enter data and exit data must be used as a pair"}
      ]
    },
    "P6_update_optimization": {
      "template": {
        "1D_partial": "!$acc data copy({{ARRAY}}({{START}}:{{END}}))",
        "2D_partial": "!$acc data copy({{ARRAY}}({{I_START}}:{{I_END}}, {{J_START}}:{{J_END}}))",
        "3D_partial": "!$acc data copy({{ARRAY}}({{I_START}}:{{I_END}}, {{J_START}}:{{J_END}}, {{K_START}}:{{K_END}}))"
      }
    }
  }
}
```

## Summary

This skill takes a **reliability-first, template-based** approach. LLM reasoning is used only for pattern detection and matching; actual code generation relies on verified templates to produce high-quality OpenACC directives.

## References

- **Source code**: github.com/jeng1220/openacc_fortran_examples
- **Target benchmarks**: NAS Parallel Benchmarks (NPB)
