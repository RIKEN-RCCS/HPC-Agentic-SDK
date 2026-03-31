---
name: gpu-porting
description: Use when porting HPC code to GPU, converting CPU kernels to GPU-accelerated code, or adding GPU support to existing applications
user-invocable: true
---

# GPU Porting Workflow

## Core Principle

Port HPC code to GPU through systematic profiling, analysis, and targeted OpenACC directives. **Every iteration runs through make-vibe MCP.** Never compile locally, never run locally, never benchmark locally.

## The Iron Law

**All GPU porting work runs through make-vibe MCP. You never compile locally, run locally, or benchmark locally. Ever.**

If you think "let me quickly test this locally first," you've already violated the workflow. Stop and use make-vibe.

---

## Mandatory Practices

| Practice | Why It Matters |
|----------|---|
| Create Makefile target before running ANY experiment | Ensures reproducibility; avoids trial-and-error locally |
| Ask user to reload make-vibe after Makefile edit | Forces make-vibe to discover new targets; prevents skipping |
| Verify GPU code produces correct results | Proves port is correct, not just fast; prevents silent bugs |
| Use r-ccs-cloud for GPU configuration | Ensures correct system settings, modules, SLURM parameters |
| Use RAPTOR to profile before porting (recommended) | Targets highest-impact functions; avoids wasted effort |
| Use Tadashi to validate loop safety (recommended) | Prevents invalid parallelization; proves correctness |
| Invoke OpenACC skill to add GPU directives | Ensures consistent, verified GPU patterns |
| Document every optimization in code comments | Makes choices reproducible for future engineers |
| Measure performance from make-vibe output only | Eliminates environmental variability; proves improvement |

---

## The Workflow

### Prerequisites

**Hard gate:** Code must compile and run correctly on CPU first. Cannot begin GPU porting on broken code.

**User must provide:**
- Directory path to source code
- Existing Makefile (or will create one)
- Target GPU system (RIKEN R-CCS, cloud, local NVIDIA, etc.)

---

### Phase 1: Setup

1. **Ask clarifying questions:**
   - Current Makefile? What compiler? Target GPU system?

2. **Invoke r-ccs-cloud skill**
   - Determine GPU partition, modules, SLURM parameters
   - Document in make-vibe.config

3. **Create make-vibe.config** in code directory:
   ```bash
   COMPILER=pgcc              # Compiler
   GPU_ARCH=sm_70             # GPU architecture
   PARTITION=gpu              # SLURM partition
   GPUS_PER_NODE=1
   TIME_LIMIT=10:00
   ```

4. **Create/update Makefile** with targets:
   - `make build` — compile with GPU flags
   - `make run` — execute on GPU
   - `make clean` — cleanup

5. **Verify make-vibe works:**
   - Run `/make-vibe build` → must succeed
   - Run `/make-vibe run` → capture baseline performance
   - If fails: debug setup until working

**Hard gate:** Cannot proceed until baseline runs through make-vibe successfully.

**Artifact:** `GPU_PORTING_SETUP.md` with baseline performance.

---

### Phase 2: Analysis & Planning

1. **Invoke RAPTOR skill** (optional but recommended)
   - Profile FP operations
   - Identify which functions consume most time
   - Document precision requirements

2. **Invoke Tadashi skill** (optional but recommended)
   - Validate loop parallelization safety
   - Identify candidate loops
   - Document dependencies

3. **Review code structure**
   - Identify GPU-suitable functions (regular loops, data parallelism)
   - Rank by performance impact
   - Estimate communication overhead

4. **Create GPU_PORTING_PLAN.md**
   - Target functions (ranked)
   - OpenACC strategy per function
   - Expected speedup vs. overhead

**Hard gate:** User must approve plan before Phase 3.

---

### Phase 3: GPU Porting (Iterative)

For each target function:

1. **Create Makefile target** with name like `gpu-test-<function>`
   ```makefile
   .PHONY: gpu-test-kernel1
   gpu-test-kernel1:
       $(COMPILER) $(CFLAGS) -acc -gpu=cc70 src/kernel.f90 -o build/test
       ./build/test < input.in > output.out
   ```

2. **Invoke OpenACC skill**
   - Add `!$acc parallel loop` or `!$acc kernels`
   - Keep changes minimal (directives only, no algorithm changes)
   - Document GPU constraints in comments

3. **Commit code changes**

4. **Tell user:** "I've created Makefile target `gpu-test-kernel1`. Please reload the make-vibe plugin."

5. **Wait for user reload confirmation**

6. **Run:** `/make-vibe gpu-test-kernel1`
   - Capture compiler output, test results, performance delta
   - All results from make-vibe output only

7. **Evaluate:**
   - Did compilation succeed?
   - Did test produce correct results?
   - Is speedup acceptable?
   - If YES: merge to main. If NO: debug and retry.

**Repeat for each GPU candidate function.**

**Hard gate:** No local compilation, no local testing, no local benchmarking. Ever.

---

### Phase 4: Full System Integration

1. **Combine all successful GPU changes** into main build targets
   - Update `make build` to enable GPU flags for all ported functions
   - Update `make run` to use GPU-optimized binary

2. **Create gpu-benchmark Makefile target:**
   ```makefile
   .PHONY: gpu-benchmark
   gpu-benchmark:
       make clean
       make build
       make run
   ```

3. **Run:** `/make-vibe gpu-benchmark`
   - Capture final system performance
   - Compare vs. baseline from Phase 1

---

### Phase 5: Verification & Documentation

1. **Run full test suite** through make-vibe
   - Numerical correctness verified
   - Different input sizes tested
   - Edge cases checked

2. **Create GPU_PORTING_REPORT.md:**
   - Each ported function with speedup
   - Total system speedup
   - Which Makefile targets correspond to each experiment
   - Known limitations

3. **Update code comments:**
   ```fortran
   !$acc parallel loop collapse(2)
   ! GPU: Hotspot from RAPTOR (60% of time)
   ! Expected speedup: 10x on H100 GPU
   ! Constraint: Memory bandwidth-limited
   do i = 1, n
     do j = 1, m
       ...
   ```

4. **Create OPTIMIZATION.md** for future engineers:
   - How to build GPU version
   - How to run on GPU
   - How to benchmark CPU vs. GPU
   - Performance tuning tips

5. **Final commit:**
   ```
   GPU Porting: X functions ported to OpenACC

   Functions ported: compute_kernel, advection, pressure_solve
   Overall speedup: 8.3x (measured via make-vibe on [system])
   All tests passing.
   ```

---

## Common Rationalizations Rejected

**"Let me quickly test this locally first"**
→ Defeats the purpose. Local environment ≠ GPU system. Makes you trust local results, tempts you to skip make-vibe next time.

**"This is simple, doesn't need a Makefile target"**
→ Simple changes hide complexity. Makefile target forces clarity and reproducibility. No shortcuts.

**"I'll create the Makefile target after I know it works"**
→ Never works. You'll get results locally, declare success, skip make-vibe. Result: GPU code untested on actual hardware.

**"I'll reload the plugin later"**
→ Breaks workflow consistency. Missing reload = make-vibe doesn't discover target = you run it locally anyway.

**"The code compiled locally, so it's ready"**
→ Local compiler ≠ GPU compiler. Different flags, optimizations, target architecture. Proof only exists via make-vibe.

**"I already tested this function"**
→ GPU testing is integration testing. Each change can break something. Full test suite required through make-vibe.

---

## Red Flags

Stop immediately if you find yourself:

- ❌ "Let me try running this locally first"
- ❌ "I'll compile and test, then create a Makefile target"
- ❌ "This is simple enough to skip make-vibe"
- ❌ "I ran `make gpu-test` locally and it worked"
- ❌ "Let me try different compiler flags without updating Makefile"
- ❌ "I'll skip the Makefile target this once"
- ❌ "I already know what will happen, so..."

If any of these appear in your thinking, you've abandoned the workflow. Return to Phase 3 step 1: create a Makefile target first.

---

## Verification Checklist

Before declaring GPU porting complete, verify:

- ✓ Every iteration created a Makefile target
- ✓ User reloaded make-vibe before each target execution
- ✓ All results captured from make-vibe output only
- ✓ No local compilation occurred
- ✓ No local testing occurred
- ✓ GPU code produces identical or numerically equivalent results to CPU
- ✓ Performance improvement is measurable and documented
- ✓ Every optimization has inline code comment explaining GPU choice
- ✓ Makefile targets are named clearly (gpu-test-<function>, gpu-benchmark)
- ✓ OPTIMIZATION.md exists with reproducibility instructions
- ✓ Final commit references performance improvement with system used

If any checkbox is false, the workflow is incomplete.

---

## When NOT to Use This Skill

- ❌ Code doesn't compile or run on CPU yet (fix build issues first)
- ❌ No GPU available on target system (use CPU optimization instead)
- ❌ Code is not performance-critical (wasted effort)
- ❌ GPU porting would break numerical accuracy unacceptably
- ❌ User cannot provide code directory with Makefile
