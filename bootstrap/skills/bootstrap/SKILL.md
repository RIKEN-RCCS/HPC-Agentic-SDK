---
name: bootstrap
description: Use when starting work on a new HPC code project to set up the right skills and create a project CLAUDE.md
user-invocable: true
---

# Bootstrap: HPC Project Setup

## Core Principle

Before any code work begins, establish a clear project context and ensure all required skills are installed and verified. This is a one-time setup that creates a `CLAUDE.md` file documenting project goals, installed tools, and mandatory workflows.

## The Iron Law

**No code optimization, porting, or tuning work begins until:**
1. Project goals are clearly defined
2. All required HPC skills are installed
3. Each skill is tested and working
4. A `CLAUDE.md` file documents the setup and rules

This prevents wasted effort on wrong tools or misconfigured environments.

---

## Mandatory Practices

| Practice | Why It Matters |
|----------|---|
| Ask clarifying questions before assuming tools | Different projects need different tools; wrong tools waste time |
| Test each skill immediately after installation | Installed ≠ working; failures caught early, not mid-project |
| Document goals in CLAUDE.md upfront | Keeps focus; prevents scope creep; guides skill selection |
| If make-vibe is installed, enforce the rule | make-vibe-only execution prevents local shortcuts that undermine reproducibility |
| Get user agreement on CLAUDE.md before proceeding | Ensures alignment on project scope, tools, and constraints |

---

## The Workflow

### Phase 1: Understand the Project

Ask the user (one question per exchange):

1. **What are your code optimization/porting goals?**
   - Examples: "Port to GPU", "Optimize performance", "Add MPI parallelism", "Reduce FP precision overhead", "Improve CI/CD"

2. **What code language and framework?**
   - C, C++, Fortran? MPI, OpenMP, other parallelism? Current state (working, broken, partial)?

3. **What's your HPC system?**
   - RIKEN R-CCS? Cloud GPU? Local cluster? Constraints (partition, nodes, time limits)?

4. **Do you need to run code remotely or locally?**
   - Locally? Remotely with SLURM? Both?

**Artifact created:** Notes on project scope, constraints, and environment.

---

### Phase 2: Determine Required Skills

Based on answers, recommend which HPC-Agentic-SDK skills are needed:

| Goal | Skills Required | Optional |
|------|-----------------|----------|
| GPU porting | OpenACC, make-vibe | RAPTOR, Tadashi, r-ccs-cloud |
| Performance tuning | RAPTOR | Tadashi, make-vibe |
| Loop optimization | Tadashi | RAPTOR, make-vibe |
| Precision reduction | RAPTOR | make-vibe |
| Remote execution | make-vibe | r-ccs-cloud (if RIKEN) |
| Any optimization | make-vibe (if remote execution) | — |

**Decision point:** If user will run experiments remotely or via HPC, make-vibe is **mandatory**. If local-only, make-vibe is optional.

Ask user to confirm the skill list:
- "For your goals, I recommend installing: X, Y, Z. Does this match your plan?"

**Artifact created:** Final skill list (required + recommended).

---

### Phase 3: Install and Verify Skills

For each skill in the list:

1. **Guide installation:**
   ```
   /plugin install SKILL_NAME
   ```

2. **Test immediately:**
   - For pure skills (RAPTOR, r-ccs-cloud): Ask user to view the skill and confirm it loaded
   - For MCP skills (make-vibe, Tadashi, OpenACC):
     - Ask user to reload Claude Code plugin
     - Test a simple invocation to confirm tools appear
     - Example for make-vibe: "Try calling a Makefile target to confirm make-vibe is working"

3. **Hard gate:** If skill fails to load, debug before proceeding.

**Artifact created:** Verification checklist — which skills are installed and tested.

---

### Phase 4: Create CLAUDE.md

Generate a `CLAUDE.md` file in the project root:

```markdown
# Project: [Project Name]

## Objectives

- [Goal 1: e.g., "Port advection kernel to NVIDIA GPU"]
- [Goal 2: e.g., "Achieve 8x speedup with <5% accuracy loss"]

## Environment

- **Code language:** [e.g., Fortran]
- **HPC system:** [e.g., RIKEN R-CCS]
- **Execution mode:** [Local / Remote SLURM / Both]

## Installed Skills

The following HPC-Agentic-SDK skills are installed and verified:

- [x] RAPTOR — Profile and optimize floating-point precision
- [x] make-vibe — Remote code execution via MCP
- [x] r-ccs-cloud — RIKEN R-CCS reference guide
- [ ] Tadashi — Validate loop parallelization
- [ ] OpenACC — Insert GPU directives

## Mandatory Workflows

### If make-vibe is installed:

**The Iron Law:** All code execution runs through make-vibe MCP. You never run `make` commands locally, never compile locally, never run code locally.

**Workflow:**
1. Edit source code locally
2. Create or update a Makefile target (e.g., `make gpu-test-kernel1`)
3. Commit changes
4. Tell the user: "I've added/updated Makefile target X. Please reload make-vibe plugin."
5. User reloads (forces make-vibe to re-parse Makefile)
6. Call `/make_<target>` MCP tool to execute on HPC
7. Parse results from tool output only

**Why:** Local environment ≠ HPC environment. Proof only exists on actual hardware via make-vibe.

### Other mandatory practices:

- Always profile before optimizing (use RAPTOR)
- Always validate loop transforms (use Tadashi if uncertain)
- Document every optimization in code comments
- Test on actual HPC system (via make-vibe)
- Never skip to implementation without a plan

## How to Proceed

1. Run the relevant HPC optimization skill (e.g., gpu-porting, profile-and-tune)
2. It will invoke other skills as needed (RAPTOR, Tadashi, OpenACC, make-vibe)
3. Follow the skill's workflow exactly
4. Use installed tools as required
5. All proof comes from make-vibe (if installed) or skill outputs

## Notes

[Project-specific notes, constraints, or known issues]
```

**Ask user to review and approve** the CLAUDE.md before proceeding.

---

### Phase 5: Finalize and Begin

Once CLAUDE.md is approved:

1. **Commit CLAUDE.md** to the repository
   ```
   git add CLAUDE.md
   git commit -m "Initialize project CLAUDE.md with goals, tools, and workflows"
   ```

2. **Summarize next steps:**
   - "Your project is set up with [X, Y, Z] skills installed."
   - "CLAUDE.md documents your goals and mandatory workflows."
   - "When you're ready, tell me which skill you'd like to run: e.g., 'Run the GPU porting workflow' or 'Profile this code with RAPTOR'."
   - "I'll invoke the skill and guide you through it."

**Hard gate:** Do not proceed with optimization/porting work until CLAUDE.md exists and user has approved it.

---

## Common Rationalizations Rejected

**"Let me just try the skill without installing all of them"**
→ Partial tools = partial results. You'll end up re-running work when you need a tool you skipped.

**"I'll create CLAUDE.md later"**
→ Never works. Without documented goals and rules, scope creep and tool misuse happen. Create it now.

**"I know I need make-vibe, but I don't want to write the Makefile rule"**
→ The Makefile IS the proof. Shortcuts skip reproducibility. Write the rule every time.

**"make-vibe is slow; let me just run locally to iterate faster"**
→ Local iterations ≠ HPC results. You'll waste more time debugging mismatches than make-vibe adds latency.

**"This project is too simple to need all this setup"**
→ Simple projects hide complexity. Setup costs ~30 mins. False starts cost hours.

---

## Red Flags

Stop immediately if:

- ❌ "Let me skip installing skill X, it's optional anyway"
- ❌ "I'll test the skill later, after I start the work"
- ❌ "I'll write CLAUDE.md once I know what I'm doing"
- ❌ "I don't need to reload make-vibe for every target change"
- ❌ "Let me just run `make` locally to check if it compiles"
- ❌ "This skill doesn't apply to my project, so I'll skip it"

If any of these appear, you've skipped the bootstrap. Return to Phase 1.

---

## Verification Checklist

Before declaring bootstrap complete, verify:

- ✓ All project goals are documented and user-approved
- ✓ HPC system constraints are understood (partition, time limits, modules, etc.)
- ✓ All required skills are installed
- ✓ Each skill has been tested and confirmed working
- ✓ CLAUDE.md exists in project root
- ✓ CLAUDE.md documents: goals, environment, installed skills, mandatory workflows
- ✓ If make-vibe is installed, CLAUDE.md includes the "never run locally" rule
- ✓ User has reviewed and approved CLAUDE.md
- ✓ CLAUDE.md is committed to the repository

If any checkbox is false, bootstrap is incomplete. Complete it before starting optimization work.

---

## When NOT to Use This Skill

- ❌ Project is already set up with a CLAUDE.md (you're done)
- ❌ Starting a simple one-off task with no long-term project context
- ❌ Running a skill on an already-bootstrapped project (use the skill directly)
