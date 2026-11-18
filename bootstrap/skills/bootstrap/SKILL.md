---
name: bootstrap
description: Use before any HPC code optimization, porting, or tuning work begins. Set up the right skills, verify they work, and create a project CLAUDE.md that documents goals and mandatory workflows.
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
| Get user agreement on CLAUDE.md before proceeding | Ensures alignment on project scope, tools, and constraints |

---

## The Workflow

### Phase 1: Explore and Understand the Project

1. **Explore the project directory:**
   - List source files to identify code language (C, C++, Fortran)
   - Check for Makefile, build scripts, configuration files
   - Read key source files to understand what the code does
   - Identify any existing parallelism (MPI, OpenMP, etc.)

2. **Ask ONE clarifying question:**
   - "I see you have [language] code for [what it does]. What's your optimization goal? (e.g., Port to GPU / Optimize performance / Add MPI / Reduce FP overhead)"

3. **Ask ONE system question:**
   - "Where will you run experiments? (localhost on your machine / R-CCS cloud)"

4. **Ask system-specific constraints (if needed):**
   - If R-CCS cloud: "Any specific constraints? (GPU type, partition, time limit, etc.)"
   - If localhost: "Any environment setup needed? (specific compiler, dependencies, etc.)"

**Artifact created:** Notes on code, goals, and execution environment.

**Hard gate:** Do NOT ask generic questions about code language, state, or HPC systems. Look at the directory first. Only ask what you can't determine by reading the project.

---

### Phase 2: Determine Required Skills

Based on answers, recommend which HPC-Agentic-SDK skills are needed:

| Goal | Skills Required | Optional |
|------|-----------------|----------|
| GPU porting | OpenACC | RAPTOR, Tadashi |
| Performance tuning | RAPTOR | Tadashi |
| Loop optimization | Tadashi | RAPTOR |
| Precision reduction | RAPTOR | — |
| R-CCS Cloud execution | rccs-cloud | — |

**Decision point:**
- For **R-CCS Cloud**, use the `rccs-cloud` plugin for cluster access and job submission.
- For **localhost**, use the project's local build and test commands.
- Optimization skills (RAPTOR, Tadashi, OpenACC) depend on the work, not the system

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
   - For pure skills (RAPTOR, OpenACC): Ask user to view the skill and confirm it loaded
   - For plugins with MCP servers (Tadashi, rccs-cloud):
     - Ask user to restart Claude Code or reconnect to the MCP servers
     - Test a simple invocation to confirm MCP tools appear

3. **If the project runs on R-CCS Cloud:**
   - Use `rccs-cloud-configuring` to set up the connection and verify access.
   - Use `rccs-cloud-submitting-jobs` to plan how the project's build and test commands will run in Slurm jobs.

4. **Hard gate:**
   - All required skills must load successfully
   - Do NOT proceed to Phase 4 until all skills are verified

**Artifact created:** Verification checklist (all skills installed, tested, and configured)

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
- **Execution system:** [Localhost / R-CCS cloud]
- **Constraints:** [e.g., GPU type, time limits, partition]

## Installed Skills and MCP Servers

The following HPC-Agentic-SDK skills and MCP servers are installed and verified:

**Skills:**
- [x] RAPTOR — Profile and optimize floating-point precision
- [x] rccs-cloud — R-CCS Cloud job submission and monitoring skills
- [ ] Tadashi (skill) — Validate loop parallelization
- [ ] OpenACC (skill) — Insert GPU directives

**MCP Servers:**
- [x] rccs-cloud-hpc — Submit and monitor jobs on R-CCS Cloud

## Mandatory Workflows

- Always profile before optimizing (use RAPTOR)
- Always validate loop transforms (use Tadashi if uncertain)
- Document every optimization in code comments
- Run performance tests on the agreed execution system. For R-CCS Cloud, record the Slurm job ID and output alongside results.
- Never skip to implementation without a plan

## How to Proceed

1. Run the relevant HPC optimization skill (e.g., gpu-porting, profile-and-tune)
2. It will invoke other skills as needed (RAPTOR, Tadashi, OpenACC)
3. Use the project's documented build and test commands.
4. Follow the skill's workflow exactly
5. Verify results against the build, test, or job output.

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

**"This project is too simple to need all this setup"**
→ Simple projects hide complexity. Setup costs ~30 mins. False starts cost hours.

---

## Red Flags

Stop immediately if:

- ❌ Asking "What language is your code?" without checking the directory first
- ❌ Asking "What's your HPC system?" with options like "Local GPU", "Cloud GPU", "Academic cluster" (we only support localhost or R-CCS cloud)
- ❌ "Let me skip installing skill X, it's optional anyway"
- ❌ "I'll test the skill later, after I start the work"
- ❌ "I'll write CLAUDE.md once I know what I'm doing"
- ❌ "This skill doesn't apply to my project, so I'll skip it"

If any of these appear, you've skipped the bootstrap. Return to Phase 1: explore the directory first, then ask focused questions.

---

## Verification Checklist

Before declaring bootstrap complete, verify:

- ✓ All project goals are documented and user-approved
- ✓ Execution system is clear (localhost or R-CCS cloud)
- ✓ All required skills are installed
- ✓ Each skill has been tested and confirmed working
- ✓ If using R-CCS Cloud, cluster access is verified and the Slurm build and test workflow is documented
- ✓ CLAUDE.md exists in project root
- ✓ CLAUDE.md documents: goals, environment, installed skills, mandatory workflows
- ✓ User has reviewed and approved CLAUDE.md
- ✓ CLAUDE.md is committed to the repository

If any checkbox is false, bootstrap is incomplete. Complete it before starting optimization work.

---

## When NOT to Use This Skill

- ❌ Project is already set up with a CLAUDE.md (you're done)
- ❌ Starting a simple one-off task with no long-term project context
- ❌ Running a skill on an already-bootstrapped project (use the skill directly)
