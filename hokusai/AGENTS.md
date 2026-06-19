# HokusaiAgent — agent instructions

Claude Code and Codex plugin for the RIKEN HOKUSAI BigWaterfall2 (HBW2)
supercomputer: two MCP servers (`hokusai-hpc` for Slurm, `hokusai-docs` for
documentation RAG) plus skills. See README.md for the user-facing overview.

HBW2 is a **CPU-first** machine: the 312-node Massively Parallel Computer (MPC)
and the 2-node large-memory server (LMC) carry the bulk of the work. There is a
small 4-node H100 GPU server for postprocessing — treat GPUs as an optional,
secondary resource, not the default.

## Design rules (read before changing code)

- **The `hokusai-hpc` tool surface mirrors the IRI Facility API** (DOE standard).
  The reference spec is **not committed** (it is ALCF's, with no redistribution
  license); fetch a working copy when you need it for coverage work —
  `curl -s https://api.alcf.anl.gov/openapi.json -o openapi.json` (git-ignored).
  Before adding, renaming, or removing a tool, check `IRI_CHECKLIST.md` — new
  tools should map to an IRI endpoint and the checklist must be updated.
  Extensions with no IRI counterpart (like `run_command_on_cluster`) are allowed
  but must be marked as such. When porting, **re-decide coverage per machine** —
  the checklist verdicts are machine-specific (an endpoint can be implementable on
  one machine and not another); see PORTING.md.
- **All cluster interaction goes through `server/hokusai_mcp/middleware.py`**
  (`run_command` / `write_remote_file`). Never shell out to ssh directly from
  tool code. Middleware enforces three conventions in one place: commands run
  under a **login shell** (Slurm on HBW2 resolves through the login profile),
  the working directory is **$HOME** (relative paths resolve there), and
  payloads travel **base64-encoded** (quote-proof). Output is capped at 200KB.
- **Never write to stdout in server code** — the MCP stdio transport uses it
  for JSON-RPC and any stray print corrupts the session. Log to stderr.
  remotemanager prints progress to stdout; middleware redirects it.
- **Tools are thin verbs; workflow knowledge lives in `plugins/hokusai/skills/`.** If you're
  writing a long docstring telling the model *when* to do something, it
  probably belongs in a SKILL.md instead.
- **The MCP runtime must be self-contained under `server/`.** Plugin metadata is
  shared across Claude Code and Codex, but `plugins/hokusai/.mcp.json` launches the servers with
  `uv tool run --from git+https://github.com/RIKEN-RCCS/Hokusai-Agent.git@main#subdirectory=server`.
  Do not depend on `CLAUDE_PLUGIN_ROOT`, Codex-specific root variables, or
  repo-root `data/` paths at runtime. Anything the MCP server needs after uv
  installation must be package data under `server/hokusai_mcp/data/`.
- **`models.py` follows PSI/J shapes** (JobSpec/ResourceSpec/JobAttributes/
  JobState). Describe work in CPU terms (nodes / processes_per_node ranks /
  cpu_cores_per_process threads / memory); `gpus` is an optional extension.
  Deviations are listed at the bottom of `IRI_CHECKLIST.md`.
- Bias to simple and maintainable. No new runtime dependencies without a strong
  reason (current set: mcp, remotemanager, httpx, numpy). Python ≥ 3.10.

## Cluster facts

- SSH destination comes from `~/.hokusai/config.json` (`ssh.host`, default
  alias `hokusai`) → `hokusai.riken.jp` (round-robins to `hokusai1..4`).
  Key-based auth only — the MCP server cannot answer password prompts.
- Scheduler is **Slurm** (sbatch/squeue/sacct/scancel/sinfo). Nodes are
  **x86_64 Intel Xeon**; build with the Intel oneAPI compilers (`module load
  intel`) and Intel MKL (`-qmkl`).
- **Every job needs `--account <projectID>`** (e.g. `RB999999`). A default lives
  in config (`account` / `HOKUSAI_ACCOUNT`) and is injected by `compute.py` when
  a JobSpec omits one. Core-time is checked with `listcpu -p <project>`.
- Partitions: `mpc` (default, ≤24h), `mpc_l` (≤72h), `lmc` (large memory),
  `gpu`/`gpu_i` (GPU server). GPUs are requested with `--gpus`. Default wall
  time 1h.
- Storage: `/home` (4 TB), `/data/<projectID>`, `/tmp_work` (scratch, purged
  after a week). Lustre — `lfs quota` for usage.

## Documentation search (RAG)

The docs source is **`server/hokusai_mcp/data/hokusai_guide.md`** — an *original*, plain-language
guide to HBW2 written for users working through the agent (facts in our own words,
not a copy of the vendor manual, so the index is freely distributable). It
deliberately omits generic HPC/compiler background and anything the agent can read
live (`sinfo`/`sacct`/`module avail`/`listcpu`); keep it that way when editing.
`rag/ingest.py` chunks it by markdown heading into `server/hokusai_mcp/data/docs_index/chunks.json`
(section text + breadcrumbs, also the BM25 corpus). The guide and the index are
both committed as package data so `uv tool run --from ...#subdirectory=server`
installs a self-contained MCP runtime.

Search uses BGE-M3 (`bge-m3:567m`) served at the shared RIKEN endpoint
`http://llm.ai.r-ccs.riken.jp:11434/v1` — both are hardcoded constants
(`EMBED_BASE_URL` / `EMBED_MODEL` in `config.py`). The only user-facing setting
is `api_key` (`HOKUSAI_EMBED_API_KEY`). When `embeddings.npy` is present and the
endpoint reachable, search is semantic (vectors aligned row-for-row to
`chunks.json`); otherwise it falls back to BM25 keyword matching over the same
chunks. `embeddings.npy` is only generated when the endpoint is reachable at
ingest time, so the committed index may be BM25-only until then.

**Do not make model or base_url user-configurable.** `embeddings.npy` is tied to
`bge-m3:567m`; a different model at query time silently produces garbage cosine
similarity. If the model ever changes, update the constants, re-run ingest, and
commit the new `embeddings.npy`. `rag/embed.py` is the only file that knows the
API dialect.

**To rebuild the index** (after editing the guide): `python -m
hokusai_mcp.rag.ingest` (add `--no-embed` to skip vectors, or omit it to compute
embeddings when the endpoint is reachable + an API key is set). Commit the
regenerated `chunks.json` (+ `embeddings.npy` if produced).

## Development workflow

```bash
cd server
python3 -m venv .venv && .venv/bin/pip install -e .   # or just use ./run.sh
./run.sh hokusai_mcp.doctor          # validate config, SSH, Slurm, embedding, index
.venv/bin/python tests/smoke.py      # live read-only test over MCP stdio
.venv/bin/python tests/smoke.py --job   # + submits a real ~5-min CPU job
.venv/bin/python -m hokusai_mcp.rag.ingest  # rebuild docs index from packaged guide
```

- The smoke tests need working cluster access (and a valid project account);
  `--job` consumes a (tiny) allocation. Run the read-only test for most changes;
  run `--job` when touching `compute.py`, `middleware.py`, or `models.py`.
- Validate the install-path runtime with:
  `uv tool run --quiet --from ./server hokusai-doctor`. The marketplace runtime
  uses the same package boundary, but from GitHub `main`.
- Test the plugin in Claude Code:
  `/plugin marketplace add <repo-path>` → `/plugin install hokusai@hokusai-marketplace`.
- Test the plugin in Codex:
  `codex plugin marketplace add <repo-path>` → open `/plugins` and install `hokusai`.
- User settings live in `~/.hokusai/config.json` (may contain an embedding API
  key — never commit it, never echo the key). The `hokusai-configuring` skill
  documents the schema.

## Repository map

```
.claude-plugin/         Claude Code marketplace manifest
.agents/plugins/        Codex marketplace manifest
plugins/hokusai/        actual plugin payload for both Claude Code and Codex
  .claude-plugin/       Claude Code plugin manifest
  .codex-plugin/        Codex plugin manifest
  .mcp.json             shared MCP launch config (uv tool run from main)
  skills/               hokusai-configuring, hokusai-submitting-jobs,
                        hokusai-monitoring-jobs, hokusai-reference, hokusai-demo
IRI_CHECKLIST.md        API coverage tracker — keep in sync with hpc_server.py
server/hokusai_mcp/
  data/                 packaged guide, static facts, and docs_index
  middleware.py         SSH layer — the only place that talks to the cluster
  models.py             PSI/J-style schemas + Slurm state normalization
  compute.py            JobSpec → sbatch, sacct/squeue parsing, account fallback
  hpc_server.py         hokusai-hpc MCP tools (IRI-grouped)
  docs_server.py        hokusai-docs MCP tools
  rag/                  embed client / index store / markdown ingest pipeline
  doctor.py             health checks (python -m hokusai_mcp.doctor)
  serving.py            shared CLI entry point
```

Skill names are machine-prefixed so both this and the AI4S plugin can be
installed at once without skill-name collisions.
