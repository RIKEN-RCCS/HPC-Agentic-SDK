# Porting Guide: Implementing a New Machine

This guide is for an agent bootstrapping a new HPC MCP server from a clone of
this repository. Read it fully before writing any code.

The goal: a working MCP plugin for a new cluster that follows the same
architecture, passes `doctor.py`, and exposes the same tool surface as
`hokusai-hpc` (adapted to the target scheduler and filesystem).

**The single most important idea in this guide:** a faithful port adapts the
machine's *character* — its resource balance, its default run mode, its
mandatory conventions — not just its strings. Three real ports exist as reference
points and they are deliberately different:

- **AI4S / GB200** (`Rikyu-Agent`) — a **GPU-first** cluster. Jobs are GPU jobs;
  the partition fixes the per-node GPU share; the default ResourceSpec requests
  a GPU.
- **HOKUSAI BigWaterfall2** (`Hokusai-Agent`) — a **CPU-first** cluster. The bulk
  is 312 CPU (MPC) nodes plus a large-memory server; only 4 GPU nodes exist, for
  postprocessing. Jobs are CPU/MPI jobs by default; GPUs are an optional extra.
- **R-CCS Cloud** (`RCCS-CloudAgent`) — a **heterogeneous research testbed**. No
  single dominant run mode: ~20 partitions spanning CPU-only, NVIDIA, AMD, and
  Intel GPU. The machine's character is hardware diversity and partition-specific
  module loading. The agent's job is guiding partition choice and module setup,
  not defaulting to one mode.

HBW2 was ported *from* the GPU-first AI4S repo. The hard part was not renaming
`rikyu`→`hokusai` — it was **flipping the defaults and emphasis** so the plugin
reflects a CPU machine: the default partition, the default ResourceSpec, the
skills, the `/demo`, and the `get_facility` blurb all had to change from "GPU" to
"CPU/MPI". If you skip this, you ship a plugin that technically works but
constantly steers users wrong.

---

## 1. Repository architecture

```
.claude-plugin/        Claude Code marketplace manifest
.agents/plugins/       Codex marketplace manifest
plugins/<machine>/     actual plugin payload for both Claude Code and Codex
  .claude-plugin/      Claude Code plugin manifest
  .codex-plugin/       Codex plugin manifest
  .mcp.json            shared MCP launch config (uv tool run from main)
  skills/              one SKILL.md per user-facing workflow
server/hokusai_mcp/
  data/                packaged static facts, original guide, docs index
  middleware.py        THE ONLY FILE THAT TALKS TO THE CLUSTER
  config.py            settings: env > file > defaults
  models.py            PSI/J-style schemas (JobSpec, Job, JobState, …)
  compute.py           scheduler translation layer (JobSpec → scripts)
  hpc_server.py        FastMCP tools, grouped by IRI API resource
  docs_server.py       docs RAG tools
  rag/                 embed / store / ingest
  doctor.py            health checks
  serving.py           shared CLI entry point
```

The plugin metadata is deliberately thin. Claude Code and Codex both read the
same plugin payload under `plugins/<machine>/`; the MCP servers themselves are
installed as a Python package from `server/` with:

```bash
uv tool run --quiet --from git+https://github.com/RIKEN-RCCS/Hokusai-Agent.git@main#subdirectory=server hokusai-hpc-mcp
uv tool run --quiet --from git+https://github.com/RIKEN-RCCS/Hokusai-Agent.git@main#subdirectory=server hokusai-docs-mcp
```

Do not use client-specific plugin-root variables for runtime data. A port must
keep the MCP package self-contained under `server/`, including docs and static
machine facts as package data.

**What is generic (keep as-is):**
- `middleware.py` — SSH layer, base64 encoding, path handling, error raising.
  Only change the `Computer(...)` constructor args if the SSH setup differs.
- `models.py` — PSI/J shapes. Keep the schema; the *defaults* (see Phase 3) are
  machine-specific. Only deviate from the shapes if the target scheduler has no
  equivalent concept (document any deviation in `IRI_CHECKLIST.md`).
- `rag/embed.py`, `rag/store.py` — generic; the embedding endpoint + model are
  the `config.EMBED_BASE_URL`/`EMBED_MODEL` constants (store falls back to BM25
  when `embeddings.npy` is absent or the endpoint is unreachable).
- `docs_server.py` — generic RAG tool surface; no changes needed.
- `serving.py` — no changes needed.
- `plugins/<machine>/.mcp.json` launch pattern — keep the uv `tool run --from ...@main#subdirectory=server`
  shape, changing only the repository URL and console script names for the new
  port.

**What is machine-specific (must be replaced):**
- `config.py` — `ssh_host()` default, `default_account()`, the embedding
  `EMBED_BASE_URL`/`EMBED_MODEL` constants (+ `embed_api_key()`), and the doc
  source (`DOCS_SOURCE`, the committed original guide here; could be a repo URL or
  site base elsewhere).
- `models.py` **defaults** — `ResourceSpec` field defaults, `JobAttributes`
  `queue_name`/`duration` defaults. These encode "what a typical job looks like"
  and must match the machine's dominant usage (Phase 3).
- `compute.py` — the scheduler translation layer (sbatch flags, sacct parsing).
  If the target uses PBS/LSF/SGE instead of Slurm, rewrite this file. The
  interface is: `render_script(spec) -> str`, `submit(spec) -> dict`,
  `get_statuses(ids) -> list[Job]`, `get_recent_statuses() -> list[Job]`,
  `cancel(job_id) -> Job | str`.
- `hpc_server.py` — the tool implementations that call scheduler commands.
  The IRI-grouped structure and tool names must be preserved; only the
  shell commands inside them change.
- `rag/ingest.py` — doc-source-specific (chunking logic); see Phase 5.
- `server/hokusai_mcp/data/hokusai_config.json` — replace with the new machine's static facts.
- `server/hokusai_mcp/data/docs_index/` — rebuild from the new machine's documentation.
- `plugins/<machine>/skills/` — replace SKILL.md content with machine-specific workflows.
- `IRI_CHECKLIST.md` — update to track coverage for the new machine.
- `plugins/<machine>/.claude-plugin/plugin.json`,
  `plugins/<machine>/.codex-plugin/plugin.json`, and both marketplace manifests
  — update names, descriptions, repository URLs, source paths, and display
  metadata for the new machine.

---

## 2. Non-negotiable design rules

Violating these will break things in non-obvious ways.

**All cluster I/O goes through `middleware.run_command` and
`middleware.write_remote_file`.** Never shell out to ssh directly from tool
code. The middleware enforces three invariants in one place:
1. Commands run under a **login shell** — schedulers resolve their
   environment through login profiles; a bare non-login shell will not find
   them.
2. The working directory is **$HOME** — relative paths resolve correctly,
   which is what users expect.
3. Payloads travel **base64-encoded** — this makes arbitrary quoting safe
   across the SSH layer.

**Use `quote_path()` for every remote path argument, never bare
`shlex.quote()`.** `shlex.quote("~/foo")` produces `'~/foo'`; single quotes
suppress tilde expansion in bash, so the shell looks for a literal directory
named `~`. `quote_path` calls `norm_path` first, stripping the `~/` prefix
(the CWD is already `$HOME`, so relative paths resolve there).

**Never write to stdout in server code.** The MCP stdio transport uses stdout
for JSON-RPC; any stray print corrupts the session. Write to stderr.
`remotemanager` prints progress to stdout; middleware redirects it.

**Error detection uses `result.returncode`, not stderr content.**
`raise_errors=False` disables remotemanager's built-in raise (which triggers
on non-empty stderr — too aggressive for commands that write benign messages
to stderr). Instead, `run_command` raises `RuntimeError` on any non-zero
exit code. FastMCP converts that to a clean MCP tool error. Callers never
need to parse error text from the return value.

**Tools are thin verbs; workflow knowledge belongs in `skills/`.**
A tool docstring should describe what it does, not when to use it or what
to do next. Long sequences of steps, retry logic, and "first do X then Y"
belong in SKILL.md files, not in docstrings.

**The IRI Facility API is the tool naming and grouping convention.**
Before adding, renaming, or removing a tool, check `IRI_CHECKLIST.md`.
Extensions with no IRI counterpart are allowed but must be marked as such
(e.g. `run_command_on_cluster`).

---

## 3. Phase 1 — Study the documentation and build a usage model

If the user provides documentation (a path, a repo, a PDF, a portal), **read it
in full before touching the cluster.** The docs are the ground truth for
scheduler type, partition names, GPU configuration, storage layout, the module
system, and site conventions. Build a mental model from the docs first; SSH
exploration (Phase 2) is to *verify and fill gaps*, not to discover from scratch.

### Don't just collect facts — build a usage model

Extracting "scheduler = Slurm, partitions = a/b/c" is necessary but not
sufficient. The docs also tell you **how the machine is actually used**, and
that decides the *defaults and emphasis* of the entire plugin. As you read, form
an opinion on:

- **Resource balance.** What is the bulk of the system? Count the nodes. Is it a
  GPU farm with a few login/CPU nodes, a CPU MPP with a handful of GPU nodes for
  postprocessing, a large-memory shop? (AI4S: GPU-first. HBW2: 312 CPU nodes vs
  4 GPU nodes → CPU-first.) The headline hardware in the docs is your tell.
- **Default run mode.** How does a *typical* job run? Pure MPI? MPI+OpenMP
  hybrid? Single-GPU training? Multi-GPU? Large-memory serial? Interactive? The
  example job scripts in the docs are the strongest signal — note which
  partition, how many ranks/threads/GPUs they use, and what they `module load`.
- **The typical job.** From the above, decide what a "hello world" submission
  should default to: which partition, how many nodes/ranks/threads, GPU or not.
- **Mandatory conventions.** Is an account/project ID required to submit? Is
  there a fair-share or core-time budget? A required proxy for outbound network?
  Module conflicts? These become defaults, validation, and skill warnings.
- **Capabilities that map to IRI endpoints.** Note what the machine can actually
  report: allocation / core-time accounting (→ `project_allocations` /
  `user_allocations`), an incidents or events feed (→ `status/incidents`), an
  async task queue (→ `task`). These decide which IRI endpoints are
  *implementable here* — a per-machine call (re-decided in Phase 4, not inherited).

**Then set the defaults and emphasis to match — this is the crux of a good port.**
Concretely, propagate the usage model into:
- `models.py` — `ResourceSpec` field defaults (e.g. default `gpus=None` on a
  CPU-first machine vs a default GPU on a GPU-first one) and `JobAttributes`
  `queue_name` (the dominant partition) and `duration` (the site default).
- `data/<machine>_config.json` and `get_facility` — describe the machine as it
  is used (lead with the dominant subsystem).
- `plugins/<machine>/skills/` and `/demo` — frame submission, monitoring, and the demo job around
  the default run mode. The demo's test job should be a *typical* job for this
  machine, not a leftover from the source repo.

Do not carry the source repo's defaults over unexamined. The most common porting
bug is shipping a GPU-first plugin onto a CPU machine (or vice versa): it runs,
but every default and every example points users the wrong way.

### Fact checklist

Record answers to these — they become the static config JSON and inform the rest:

- What scheduler is used? (Slurm / PBS / LSF / other)
- What is the dominant workload and the default partition?
- What are the partition/queue names and their resource limits (nodes, cores,
  memory, wall time)?
- **How are GPUs requested?** The flag varies by site: `--gpus`,
  `--gpus-per-node`, or `--gres=gpu:<type>:N`. Confirm which, and whether GPUs
  are central or incidental.
- Is an **account/project ID required** to submit? What does it look like?
- What are the storage tiers, their paths, and any scratch auto-purge rules?
- What container runtime is available (Singularity/Apptainer, pyxis/enroot)?
- What is the SSH hostname / alias convention?
- What modules exist and how is the module system loaded? Any conflicts?

Fill in `server/<package>/data/<machine>_config.json` from the docs before
writing any tools. `get_facility` should return accurate, usage-aware data from
day one.

---

## 4. Phase 2 — Explore the machine

With the docs as context, use `run_command_on_cluster` to verify assumptions and
fill in anything the docs left ambiguous. Prefer targeted commands that confirm
specific facts over broad exploration.

**Confirm scheduler:**
```bash
which sbatch squeue sacct      # Slurm
which qsub qstat               # PBS/Torque
which bsub bjobs               # LSF
<scheduler> --version
```

**Job submission primitives:** submit a trivial job (`hostname`) on the default
partition and observe the real output — this pins the exact format your parsers
must handle and confirms whether an account is required:
- What does a successful submit print? (Slurm: `Submitted batch job <id>`)
- Does submission fail without `--account`? What does the error say?
- What does status/accounting output look like field by field?
- Confirm the **GPU request flag** with a 1-GPU job on the GPU partition (if any).

**Filesystem:**
```bash
echo $HOME $SCRATCH              # confirm env var names
df -h                            # storage tiers
ls -la $HOME                     # home layout
```

**Container runtime:** if the docs mention a container runtime, probe it on a
compute node before committing to it in `compute.py`. On AI4S, pyxis/enroot was
documented as available but broken in practice (`/run/user/<uid>` absent on
compute nodes) — `singularity exec` worked. HBW2 uses Singularity too. Trust
running experiments over documentation here.

---

## 5. Phase 3 — Adapt config and models

**`config.py`:**
- Change `ssh_host()` default to the new machine's SSH alias/hostname.
- Implement `default_account()` if the scheduler requires a project/account, so
  jobs that omit one still submit (the value comes from config / env).
- Set `EMBED_BASE_URL`/`EMBED_MODEL` to the embedding endpoint + model. These are
  hardcoded constants — only `embed_api_key()` is user-configurable, because the
  committed `embeddings.npy` is tied to the model. The embedding endpoint is
  often **shared infrastructure** reusable across machines at the same site
  (AI4S and HBW2 use the same RIKEN BGE-M3 endpoint); don't assume it's
  machine-specific. Without a key or endpoint, search degrades to BM25.
- Keep `DOCS_SOURCE`, `DOCS_INDEX_DIR`, and the static cluster config under
  `server/<package>/data/` and load them as package data. Environment overrides
  may exist for development, but the installed MCP runtime must not need the repo
  root or a plugin-root variable to find its data.
- Point `DOCS_SOURCE` at the new machine's original markdown guide and set
  `DOCS_SITE_BASE`.
- Keep the env-var precedence chain: `HOKUSAI_HOST`, `HOKUSAI_ACCOUNT`,
  `HOKUSAI_EMBED_API_KEY`, `HOKUSAI_CONFIG`.

**`models.py`:**
The PSI/J shapes (`JobSpec`, `ResourceSpec`, `JobAttributes`, `JobState`)
are intentionally generic — keep the shapes. **Set the defaults from your Phase 1
usage model** (see "set the defaults and emphasis to match"): the default
partition, default ranks/threads, and whether the default job requests a GPU.
This is where the machine's character lives.

Only deviate from the shapes if the target scheduler has a concept that genuinely
cannot be mapped (e.g. PBS's `-l nodes=1:ppn=4` has no direct IRI analogue), and
document deviations in `IRI_CHECKLIST.md`. The GPU field is a per-site extension
(`gpus` → `--gpus` on HBW2; `gpus_per_node` → `--gpus-per-node` on AI4S); name it
for the flag the machine actually uses.

`map_slurm_state()` must be replaced with `map_<scheduler>_state()` if not Slurm.
The normalized states are fixed: `QUEUED`, `ACTIVE`, `COMPLETED`, `FAILED`,
`CANCELED`, `HELD`, `UNKNOWN`.

---

## 6. Phase 4 — Implement the scheduler layer

**`compute.py`** is the only file that knows the scheduler dialect. Rewrite it if
needed, but keep the same interface:

| function | what it must do |
|---|---|
| `render_script(spec) -> str` | JobSpec → submission script string |
| `submit(spec) -> dict` | write script, submit, return `{job_id, script_path}` |
| `get_statuses(ids) -> list[Job]` | fetch normalized status for given IDs |
| `get_recent_statuses() -> list[Job]` | last N days for current user |
| `cancel(job_id) -> Job\|str` | cancel and return final state |

Notes from the existing ports:
- **GPU flag** — emit whatever the site uses (`--gpus`, `--gpus-per-node`,
  `--gres=gpu:<type>:N`), and only when GPUs are actually requested.
- **Required account** — inject `config.default_account()` in `render_script`
  when `attributes.account` is unset, so CPU-first machines that mandate a
  project still submit.
- Scripts are written under `~/.hokusai/jobs/<name>-<timestamp>.sh` via
  `write_remote_file` for auditability.
- **Containers** — prefer whatever mechanism works reliably. On AI4S,
  `singularity exec` was chosen over pyxis/enroot because `/run/user/<uid>` is
  absent on compute nodes. Probe before assuming.

**`hpc_server.py`:** the filesystem tools (`fs_ls`, `fs_stat`, `fs_view`, etc.)
are fully generic — standard POSIX, no changes. The compute and status tools
call into `compute.py` and are largely generic; update only docstrings to reflect
the machine's conventions. The account tools (`get_projects`, `get_project`) are
scheduler-specific; rewrite the `sacctmgr` calls for the target system.

Test each tool with `run_command_on_cluster` first to see raw output, then write
the parser.

### Re-decide IRI API coverage for *this* machine

The `IRI_CHECKLIST.md` verdicts (✅ implement / 🔜 next / ❌ defer) are
**machine-specific — never inherit them from the source repo.** A port that
copies the source's coverage will both miss endpoints the new machine *can*
support and carry tools the new machine doesn't need. Walk every IRI endpoint and
re-decide it against *this* machine's capabilities (the ones you noted in Phase 1):

- **defer → implement.** AI4S deferred `.../project_allocations` and
  `user_allocations` ("no allocation accounting"). HBW2 exposes per-project
  core-time budgets via `listcpu -p <project>`, so on HBW2 those endpoints are
  implementable — *same endpoint, opposite verdict.*
- **implement → drop.** A tool that earns its keep on the source (e.g. a live
  `nvidia-smi` GPU helper on a GPU-first machine) may be pointless on the target
  (a CPU-first machine) — don't carry it just because it was there.

Process: the reference IRI spec is **not committed** (it is ALCF's, with no
redistribution license) — fetch a working copy first:
`curl -s https://api.alcf.anl.gov/openapi.json -o openapi.json` (git-ignored).
Then go through `IRI_CHECKLIST.md` (and that spec) row by row, and for each
endpoint decide implement / defer for the target — updating the verdict and note,
and implementing the endpoints that newly apply. Mark the source-vs-target
difference in the note so the decision is auditable.

---

## 7. Phase 5 — Docs RAG

The retrieval pipeline is generic; only **`ingest.py` is doc-source-specific**.
`ingest.py` must produce a list of `{breadcrumb, url, text}` chunks from whatever
the source is. HBW2's source is
**`server/hokusai_mcp/data/hokusai_guide.md`** — an *original*, plain-language
guide we wrote (see "Write the guide, don't copy it" below), so `ingest.py` just
chunks markdown by heading:

```bash
python -m hokusai_mcp.rag.ingest             # bundled guide + embeddings
python -m hokusai_mcp.rag.ingest --no-embed  # keyword-only index
```

Chunk by the document's natural structure (markdown headings) and carry a
breadcrumb so retrieval and the model both see the context. If a machine's source
is something other than markdown (a mkdocs repo, a website, a PDF), swap the
extraction/chunking accordingly — but the output contract stays `{breadcrumb,
url, text}`. Each chunk's searchable text is defined by `store.chunk_text` so the
BM25 and embedding paths index the same representation.

### Write the guide, don't copy it

Vendor user guides are typically **copyrighted** — committing their text (or an
extracted/chunked copy of it) into a distributable repo is reproduction. Facts
are not copyrightable, so the right move is to author an *original* guide in your
own words: site-specific facts that shape how a user asks for work, and pointers
to live state for anything that changes. Deliberately **omit** generic HPC/Linux
background the model already knows, command/flag references, job-script
boilerplate, and anything queryable on the front end (`sinfo`/`sacct`/`module
avail`/quota/budget) — the agent reads those live. The result is short, stays
current, and is freely distributable. (HBW2 went this route after initially
ingesting the vendor PDF; the PDF is not committed.)

Embeddings use the shared endpoint (`EMBED_BASE_URL`/`EMBED_MODEL` constants);
ingest needs an API key to compute them and falls back to a BM25-only index
without one. At query time, `store.py` uses vectors when `embeddings.npy` exists
and the endpoint is reachable, else falls back to BM25 over the same chunks.

**Commit both `chunks.json` and `embeddings.npy` as package data** so the uv
installed server can search docs without needing the repository checkout. The
embedding model is locked to whatever was used at ingest time — never make it
user-configurable; a different model at query time silently produces wrong
cosine-similarity results. Re-run ingest if the model ever changes.

---

## 8. Phase 6 — Skills

Each skill is a `SKILL.md` that tells the agent *when* and *how* to use the
tools for a specific workflow. Port these:

| skill | what it covers |
|---|---|
| `configuring` | first-time setup, SSH config, account, config.json |
| `submitting-jobs` | building a JobSpec, common patterns, container jobs |
| `monitoring-jobs` | polling, reading output, diagnosing failures |
| `<machine>-reference` | machine-specific quick reference (rename as needed) |
| `demo` | end-to-end walkthrough, incl. a *typical* test job |

Do more than swap partition names and storage paths: **re-frame each skill around
the machine's default run mode** (from Phase 1). On a CPU-first machine,
`submitting-jobs` leads with MPI/OpenMP rank/thread layout and `module load`s,
and the demo job is a CPU job; on a GPU-first machine it leads with GPUs. The
failure-mode lists, too, should reflect what actually goes wrong here (e.g.
"missing account / out of core-time", "OMP_NUM_THREADS unset", "module conflict").

---

## 9. Phase 7 — Plugin packaging

Keep Claude Code and Codex packaging side by side:

- Root `.claude-plugin/marketplace.json` for Claude Code.
- Root `.agents/plugins/marketplace.json` for Codex.
- `plugins/<machine>/.claude-plugin/plugin.json` and
  `plugins/<machine>/.codex-plugin/plugin.json` as client-specific manifests.
- `plugins/<machine>/.mcp.json` as the shared MCP server config for both
  clients.

Both marketplace catalogs must point at the real plugin directory, for example
`./plugins/hokusai`. Do not point Codex at `./`; the CLI may add the marketplace
source but then list zero available plugins.

The MCP launch command should be client-neutral and uv-based:

```json
{
  "command": "uv",
  "args": [
    "tool",
    "run",
    "--quiet",
    "--from",
    "git+https://github.com/<owner>/<repo>.git@main#subdirectory=server",
    "<machine>-hpc-mcp"
  ]
}
```

Use `main`, not a pinned tag, for this repository family. That means the MCP tool
surface must stay backward-compatible with already-installed skill text: add
tools and fields freely, but avoid renaming/removing tools or changing response
shapes without a transition period.

Before changing `plugins/<machine>/.mcp.json`, make sure the local package path works:

```bash
uv tool run --quiet --from ./server <machine>-doctor
```

If this fails because data is missing, fix package data first. Do not paper over
it by adding client-specific root variables.

### README format

`README.md` must follow the standard format used across this plugin family:

1. **`# <AgentName>`** — one-liner ending exactly with `"all from the agent."`:
   `Claude Code and Codex plugin for the RIKEN **<machine>** — submit and monitor
   Slurm jobs, manage files on the cluster, and search the built-in documentation,
   all from the agent.`

2. **One characterization sentence** describing the machine's dominant run mode
   (CPU-first, GPU-first, heterogeneous testbed, etc.) and what that means for
   users. Keep it to one sentence; details belong in skills.

3. **`## Install`** with three subsections:
   - `### Prerequisite: uv` — the standard brew/curl block plus the "restart
     Claude Code or Codex" note. Copy verbatim from an existing README.
   - `### Claude Code` — three commands: `/plugin marketplace add <owner>/<repo>`,
     `/plugin install <machine>@<machine>-marketplace`, `/reload-plugins`.
   - `### Codex` — one command: `codex plugin marketplace add <owner>/<repo>`,
     then the prose: open `/plugins`, install `<machine>`, start a new thread,
     run `/<machine>-demo` to verify.

4. **`## Configuration`** — config file path, minimal JSON, one-sentence field
   explanation with the env var override, then the embedding key block (same
   `RCCS_EMBED_API_KEY` / BM25 fallback prose for all machines in this family).

No other top-level sections. Extra context belongs in `AGENTS.md` (developer
guidance) or skills (workflow guidance), not the README.

---

## 10. Phase 8 — Validate

**`doctor.py`** runs all health checks in order:
1. Config file present and parseable
2. SSH reachable
3. Scheduler CLI responds
4. Embedding endpoint responds (dim check) — a warning, not a failure, when no
   API key is set or the endpoint is off-network (BM25 still works)
5. Docs index has chunks (+ embeddings)

Extend `doctor.py` for any new checks the machine needs. All checks must print
`✓`/`!`/`✗` and return a bool; `main()` exits non-zero if a required check fails.

**Offline validation** (no cluster needed): byte-compile everything, import both
servers, render a JobSpec for the default *and* GPU cases (confirm the right
flags and the account fallback), load the docs index from package data, and run a
couple of `search_docs` queries (confirm `method=vector` with a key, `bm25`
without).

**Install-path validation**: run the uv package command exactly as plugin users
will run it. Use `--from ./server` locally before pushing, then the GitHub `main`
URL after the package-data refactor lands on `main`.

**Smoke tests** (`tests/smoke.py`): the read-only suite must pass without a
cluster allocation; the `--job` suite submits a real *typical* job (a CPU job on
a CPU-first machine). Run `--job` last, only when everything else is green, and
make container steps skip gracefully if the image is absent.

---

## 11. Common failure modes and fixes

| symptom | cause | fix |
|---|---|---|
| Defaults/skills steer users wrong | source repo's usage model carried over unexamined | set ResourceSpec/queue defaults, skills, and demo from the target's actual run mode (Phase 1) |
| Plugin works from checkout but fails after install | MCP server reads repo-root files that uv did not install | move runtime files under `server/<package>/data/` and include them in package data |
| Claude Code works but Codex fails, or vice versa | MCP config depends on client-specific plugin root variables | keep `.mcp.json` uv-based and client-neutral |
| First MCP startup cannot find `uv` | user installed plugin before installing uv or PATH was not refreshed | install uv, restart the client, then reload/reinstall the plugin |
| Missing endpoints the machine could serve, or dead tools it can't | inherited the source's IRI coverage verdicts | re-decide every `IRI_CHECKLIST.md` row against the target's real capabilities (Phase 4) |
| GPUs never allocate / flag rejected | wrong GPU flag for the site | confirm `--gpus` vs `--gpus-per-node` vs `--gres`; emit only when GPUs requested |
| Every job rejected at submit | scheduler requires an account/project | add `default_account()` + inject it in `render_script` |
| Scheduler commands not found | non-login shell | ensure `bash -l` in middleware template |
| `'~/foo'`: no such file | bare `shlex.quote` on a tilde path | use `quote_path()` |
| MCP session corrupts / JSON parse error | something printed to stdout | redirect to stderr |
| sbatch exits 0 but job never appears | script syntax error | check `~/.hokusai/jobs/` script manually |
| Vector search returns garbage | wrong model at query time | lock model as constant, never user-configurable |
| Docs ingest produces junk chunks | chunker assumes the wrong source format | adapt `ingest.py` to the real source (repo/PDF/site); chunk by headings |
| Tool always succeeds even when it fails | `raise_errors=False` without returncode check | check `result.returncode != 0` |
| Container job fails on compute node | pyxis/enroot needs `/run/user/<uid>` | use `singularity exec` instead |
| SSH times out mid-session | login shell profile is slow | profile the login shell; disable slow module init |
