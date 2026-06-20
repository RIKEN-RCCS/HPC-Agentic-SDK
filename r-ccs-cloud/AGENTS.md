# RCCS-CloudAgent — agent instructions

Claude Code and Codex plugin for the RIKEN R-CCS Cloud: two MCP servers
(`rccs-cloud-hpc` for Slurm, `rccs-cloud-docs` for documentation RAG) plus
skills. See README.md for the user-facing overview.

The R-CCS Cloud is a **heterogeneous research testbed**: many partition
families covering CPU-only (A64FX, x86_64), NVIDIA GPU, AMD GPU, and Intel GPU
hardware. There is no single dominant run mode. The defining character of this
machine is: **partition selection determines everything** — the hardware family,
the required modules, the GPU flag, and even the OS. The agent must guide users
through partition choice and module loading every time.

## Design rules (read before changing code)

- **The `rccs-cloud-hpc` tool surface mirrors the IRI Facility API** (DOE standard).
  The reference spec is **not committed** (it is ALCF's, with no redistribution
  license); fetch a working copy when needed:
  `curl -s https://api.alcf.anl.gov/openapi.json -o openapi.json` (git-ignored).
  Before adding, renaming, or removing a tool, check `IRI_CHECKLIST.md` — new
  tools should map to an IRI endpoint and the checklist must be updated.
- **All cluster interaction goes through `server/cloud_mcp/middleware.py`**
  (`run_command` / `write_remote_file`). Never shell out to ssh directly from
  tool code. Middleware enforces three conventions in one place: commands run
  under a **login shell**, the working directory is **$HOME**, and payloads
  travel **base64-encoded** (quote-proof). Output is capped at 200KB.
- **Never write to stdout in server code** — the MCP stdio transport uses it
  for JSON-RPC and any stray print corrupts the session. Log to stderr.
  remotemanager prints progress to stdout; middleware redirects it.
- **Tools are thin verbs; workflow knowledge lives in `plugins/rccs-cloud/skills/`.** If
  you're writing a long docstring telling the model *when* to do something, it
  probably belongs in a SKILL.md instead.
- **The MCP runtime must be self-contained under `server/`.** Plugin metadata is
  shared across Claude Code and Codex, but `plugins/rccs-cloud/.mcp.json` launches
  the servers with
  `uv tool run --from git+https://github.com/RIKEN-RCCS/RCCS-CloudAgent.git@main#subdirectory=server`.
  Do not depend on `CLAUDE_PLUGIN_ROOT`, Codex-specific root variables, or
  repo-root `data/` paths at runtime. Anything the MCP server needs after uv
  installation must be package data under `server/cloud_mcp/data/`.
- **`models.py` follows PSI/J shapes** (JobSpec/ResourceSpec/JobAttributes/
  JobState). The GPU field is `gpus` → `--gpus=<n>` (most GPU partitions).
  Exceptions: `qc-gh200` and `ng-dgx-m[0-3]` are unified CPU+GPU superchips;
  no `--gpus` flag is emitted for them when `gpus` is unset.
- Bias to simple and maintainable. No new runtime dependencies without a strong
  reason (current set: mcp, remotemanager, httpx, numpy). Python ≥ 3.10.

## Cluster facts

- SSH destination from `~/.rccs-cloud/config.json` (`ssh.host`, default alias
  `rccs-cloud`) → `login.cloud.r-ccs.riken.jp`. Key-based auth only.
- Scheduler is **Slurm**. `source /etc/profile` is required in every batch
  script before any `module` commands; `render_script` emits it automatically.
- **No project/account ID required** — jobs without `--account` use the user's
  default Slurm account. `default_account()` is not implemented.
- Submitted scripts are kept in `~/.rccs-cloud/jobs/` for auditability.
- Partitions and their module commands: see `data/cloud_config.json` and
  the Module Loading section of `data/cloud_guide.md`.

## Documentation search (RAG)

The docs source is **`server/cloud_mcp/data/cloud_guide.md`** — an *original*,
plain-language guide written for users working through the agent (facts in our
own words, not the vendor manual, so the index is freely distributable). It
deliberately omits generic HPC/Linux background and anything the agent can read
live (`sinfo`/`sacct`/`module avail`/disk usage); keep it that way when editing.

`rag/ingest.py` chunks the guide by markdown heading into
`server/cloud_mcp/data/docs_index/chunks.json`. Run it after editing the guide:
```bash
server/run.sh cloud_mcp.rag.ingest
```

Search uses BGE-M3 (`bge-m3:567m`) served at the shared RIKEN endpoint
`http://llm.ai.r-ccs.riken.jp:11434/v1` — both are hardcoded constants in
`config.py`. The only user-facing setting is `api_key` (`RCCS_CLOUD_EMBED_API_KEY`
or the shared fallback `RCCS_EMBED_API_KEY`). Without it, search falls back to
BM25 keyword matching. `embeddings.npy` is committed as package data when
available; `chunks.json` is always committed.

**Do not make model or base_url user-configurable.** `embeddings.npy` is tied to
`bge-m3:567m`; a different model at query time silently produces garbage cosine
similarity. If the model ever changes, update the constants, re-run ingest, and
commit the new `embeddings.npy`.

## Development workflow

```bash
cd server
python3 -m venv .venv && .venv/bin/pip install -e .   # or just use ./run.sh
./run.sh cloud_mcp.doctor          # validate config, SSH, Slurm, embedding, index
.venv/bin/python tests/smoke.py    # live read-only test over MCP stdio
.venv/bin/python tests/smoke.py --job   # + submits a real ~5-min CPU job on genoa
.venv/bin/python -m cloud_mcp.rag.ingest  # rebuild docs index from bundled guide
```

- The smoke tests need working cluster access; `--job` consumes a (tiny)
  allocation on genoa. Run the read-only test for most changes; run `--job`
  when touching `compute.py`, `middleware.py`, or `models.py`.
- Test the plugin in Claude Code:
  `/plugin marketplace add <repo-path>` → `/plugin install rccs-cloud@rccs-cloud-marketplace`.
- Test the plugin in Codex:
  `codex plugin marketplace add <repo-path>` → open `/plugins` and install `rccs-cloud`.
- Validate the install-path runtime with:
  `uv tool run --quiet --from ./server rccs-cloud-doctor`.
- User settings live in `~/.rccs-cloud/config.json` (may contain an embedding API
  key — never commit it, never echo the key). The `rccs-cloud-configuring` skill
  documents the schema.

## Repository map

```
.claude-plugin/            Claude Code marketplace manifest
.agents/plugins/           Codex marketplace manifest
plugins/rccs-cloud/        actual plugin payload for both Claude Code and Codex
  .claude-plugin/          Claude Code plugin manifest
  .codex-plugin/           Codex plugin manifest
  .mcp.json                shared MCP launch config (uv tool run from main)
  skills/                  rccs-cloud-configuring, rccs-cloud-submitting-jobs,
                           rccs-cloud-monitoring-jobs, rccs-cloud-reference,
                           rccs-cloud-demo
IRI_CHECKLIST.md           API coverage tracker — keep in sync with hpc_server.py
server/cloud_mcp/
  data/                    packaged guide, static config, and docs_index
  middleware.py            SSH layer — the only place that talks to the cluster
  models.py                PSI/J-style schemas + Slurm state normalization
  compute.py               JobSpec → sbatch, sacct/squeue parsing
  hpc_server.py            rccs-cloud-hpc MCP tools (IRI-grouped)
  docs_server.py           rccs-cloud-docs MCP tools
  rag/                     embed client / index store / markdown ingest pipeline
  doctor.py                health checks (python -m cloud_mcp.doctor)
  serving.py               shared CLI entry point
```

Skill names are machine-prefixed so this plugin can be installed alongside the
Hokusai and Rikyu plugins without skill-name collisions.
