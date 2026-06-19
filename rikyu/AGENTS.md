# RikyuAgent — agent instructions

Claude Code and Codex plugin for the RIKEN AI4S supercomputer: two MCP servers
(`rikyu-hpc` for Slurm, `rikyu-docs` for documentation RAG) plus skills. See
README.md for the user-facing overview.

## Design rules (read before changing code)

- **The `rikyu-hpc` tool surface mirrors the IRI Facility API** (DOE standard).
  The reference spec is **not committed** (it is ALCF's, with no redistribution
  license); fetch a working copy when you need it for coverage work —
  `curl -s https://api.alcf.anl.gov/openapi.json -o openapi.json` (git-ignored).
  Before adding, renaming, or removing a tool, check `IRI_CHECKLIST.md` — new
  tools should map to an IRI endpoint and the checklist must be updated.
  Extensions with no IRI counterpart (like `run_command_on_cluster`) are allowed
  but must be marked as such. When porting, **re-decide coverage per machine** —
  the checklist verdicts are machine-specific (an endpoint can be implementable on
  one machine and not another); see PORTING.md.
- **All cluster interaction goes through `server/rikyu_mcp/middleware.py`**
  (`run_command` / `write_remote_file`). Never shell out to ssh directly from
  tool code. Middleware enforces three conventions in one place: commands run
  under a **login shell** (Slurm on AI4S is invisible to non-login shells),
  the working directory is **$HOME** (relative paths resolve there), and
  payloads travel **base64-encoded** (quote-proof). Output is capped at 200KB.
- **Never write to stdout in server code** — the MCP stdio transport uses it
  for JSON-RPC and any stray print corrupts the session. Log to stderr.
  remotemanager prints progress to stdout; middleware redirects it.
- **Tools are thin verbs; workflow knowledge lives in `plugins/rikyu/skills/`.** If you're
  writing a long docstring telling the model *when* to do something, it
  probably belongs in a SKILL.md instead.
- **The MCP runtime must be self-contained under `server/`.** Plugin metadata is
  shared across Claude Code and Codex, but `plugins/rikyu/.mcp.json` launches the
  servers with `uv tool run --from git+https://github.com/RIKEN-RCCS/Rikyu-Agent.git@main#subdirectory=server`.
  Do not depend on `CLAUDE_PLUGIN_ROOT`, Codex-specific root variables, or
  repo-root `data/` paths at runtime. Anything the MCP server needs after uv
  installation must be package data under `server/rikyu_mcp/data/`.
- **`models.py` follows PSI/J shapes** (JobSpec/ResourceSpec/JobAttributes/
  JobState). Deviations are listed at the bottom of `IRI_CHECKLIST.md` — add
  to that list if you introduce one.
- Bias to simple and maintainable. No new dependencies without a strong
  reason (current set: mcp, remotemanager, httpx, numpy). Python ≥ 3.10.

## Cluster facts (verified live)

- SSH destination comes from `~/.rikyu/config.json` (`ssh.host`, default
  alias `rikyu`) → `login01.ai.r-ccs.riken.jp`. Key-based auth only — the
  MCP server cannot answer password prompts.
- Nodes are **aarch64** (NVIDIA Grace + GB200, 4 GPUs/node, 216 nodes).
  x86_64 binaries and wheels do not run there.
- The **partition fixes the per-node resource share** (1n1gpu … 4n4gpu-p;
  36 CPUs + 400GB per GPU). Jobs use `--gpus-per-node`, never `--gres`.
  Default walltime 12h, max 96h (4n4gpu-p unlimited).
- `$USER_SCRATCH_DIR` = node-local NVMe (~7TB), deleted when the job ends.

## Embedding / semantic search

Docs search uses BGE-M3 (`bge-m3:567m`) served at
`http://llm.ai.r-ccs.riken.jp:11434/v1` — both are hardcoded constants
(`EMBED_BASE_URL` / `EMBED_MODEL` in `config.py`). The only user-facing
setting is `api_key` (`RIKYU_EMBED_API_KEY`). Without it, search falls back
to BM25.

**Do not make model or base_url user-configurable.** `embeddings.npy` is
committed to the repo and is tied to `bge-m3:567m`; using a different model
at query time silently produces garbage results. If the model ever changes,
update the constants, re-run ingest, and commit the new `embeddings.npy`.

`rag/embed.py` is the only file that knows the API dialect.

**To rebuild the index with embeddings:** run
`python -m rikyu_mcp.rag.ingest` — produces
`server/rikyu_mcp/data/docs_index/embeddings.npy` alongside `chunks.json`.
Commit both files as package data so the uv-installed server works without a
network round-trip to re-embed.

## Development workflow

```bash
cd server
python3 -m venv .venv && .venv/bin/pip install -e .   # or just use ./run.sh
./run.sh rikyu_mcp.doctor          # validate config, SSH, Slurm, endpoint, index
.venv/bin/python tests/smoke.py    # live read-only test over MCP stdio
.venv/bin/python tests/smoke.py --job   # + submits a real 5-min 1-GPU job
.venv/bin/python -m rikyu_mcp.rag.ingest  # rebuild docs index (embeds if configured)
```

- The smoke tests need working cluster access; `--job` consumes a (tiny)
  allocation. Run the read-only test for most changes; run `--job` when
  touching `compute.py`, `middleware.py`, or `models.py`.
- Test the plugin in Claude Code:
  `/plugin marketplace add <repo-path>` → `/plugin install rikyu@rikyu-marketplace`.
- Test the plugin in Codex:
  `codex plugin marketplace add <repo-path>` → open `/plugins` and install `rikyu`.
- Validate the install-path runtime with:
  `uv tool run --quiet --from ./server rikyu-doctor`. The marketplace runtime
  uses the same package boundary, but from GitHub `main`.
- User settings live in `~/.rikyu/config.json` (may contain an embedding API
  key — never commit it, never echo the key). The `ai4s-configuring` skill
  documents the schema.
- The docs RAG indexes https://github.com/RIKEN-RCCS/ai4s_early_access
  (markdown source of the official guide). The embedding endpoint is any
  OpenAI-compatible `/v1/embeddings` server; with none configured, search
  falls back to BM25. `rag/embed.py` is the only file that knows the dialect.

## Repository map

```
.claude-plugin/        Claude Code marketplace manifest
.agents/plugins/       Codex marketplace manifest
plugins/rikyu/         actual plugin payload for both Claude Code and Codex
  .claude-plugin/      Claude Code plugin manifest
  .codex-plugin/       Codex plugin manifest
  .mcp.json            shared MCP launch config (uv tool run from main)
  skills/              ai4s-configuring, ai4s-submitting-jobs,
                       ai4s-monitoring-jobs, ai4s-reference, ai4s-demo
IRI_CHECKLIST.md       API coverage tracker — keep in sync with hpc_server.py
server/rikyu_mcp/
  data/                packaged static facts and docs_index
  middleware.py        SSH layer — the only place that talks to the cluster
  models.py            PSI/J-style schemas + Slurm state normalization
  compute.py           JobSpec → sbatch, sacct/squeue parsing
  hpc_server.py        rikyu-hpc MCP tools (IRI-grouped)
  docs_server.py       rikyu-docs MCP tools
  rag/                 embed client / index store / ingest pipeline
  doctor.py            health checks (python -m rikyu_mcp.doctor)
  serving.py           shared CLI entry point
```

Skill names are machine-prefixed so this and the Hokusai plugin can be
installed at once without collisions.
