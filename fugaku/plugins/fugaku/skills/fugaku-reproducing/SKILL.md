---
name: fugaku-reproducing
description: Use when the user asks to make a result reproducible, shareable, or turned into a notebook/script — or proactively suggest it after a chunk of exploratory job/file work that produced something worth preserving. Builds a Jupyter notebook that replays the real Fugaku workflow via hpc_agent_core.client, not a hand-copied SSH script.
user-invocable: true
---

# Turning a session into a reproducible notebook

Build a linear Jupyter notebook that reproduces what you and the user just
did, by calling the same MCP tool surface you've been using, via
`hpc_agent_core.client`.

## Your two capabilities

1. **The MCP tools already registered in this session** (`get_resources`,
   `submit_job`, `fs_download`, ...) — use these normally for the task
   itself, exactly as always.
2. **Python code inside the notebook file you produce**, using
   `hpc_agent_core.client`. This is the only place that code runs.

Everything you need for #2 is written out below. Use it directly.

## Connecting — copy this exactly

```python
from hpc_agent_core.client import connect_sync, pinned_params

CACHE_DIR = "./.hpc_cache/<short-name-for-this-notebook>"
hpc = connect_sync(
    pinned_params(
        "https://github.com/RIKEN-RCCS/Fugaku-Agent.git",
        "fugaku-hpc-mcp",
        ref="main",
        subdirectory="server",
    ),
    mode="lazy",
    cache_dir=CACHE_DIR,
)
```

This launches the server the same way `uv tool run` does for everyone —
nothing else needs to be installed to run this notebook.

## Full skeleton

```python
job = hpc.submit_job(spec={...})              # whatever the real spec was
status = hpc.wait_for_job(job["job_id"])
result = hpc.fs_download(path="...", local_path="./downloads/result.json")

hpc.close()
```

No `await`, no `async with` anywhere — `connect_sync` gives plain blocking
calls. `wait_for_job` and `fs_download` already cache correctly on their
own (terminal poll result only; real downloaded bytes) — call them exactly
like this, no extra logic needed around them.

## Caching modes

| mode | behavior | use it for |
|---|---|---|
| `live` | always hits the real cluster | the first real run, to validate |
| `lazy` | cache hit if present, else live | iterating on later cells |
| `replay` | cache only, zero SSH | sharing the finished notebook |

**A real `submit_job` on Fugaku consumes allocation time on the user's
project group.** A `mode="live"` (or `"lazy"` on a cache miss) run of a cell
containing `submit_job` submits a real `pjsub` job — tell the user what
will be submitted before running that cell for real, the same as you would
outside this workflow.

## Where the notebook file goes

The user's own project directory, or wherever they say. It is a new file
for their work — not something written into any plugin installation or
repository.

## Steps, in order

1. **Write the minimal clean sequence of calls that produces the user's
   actual result** — not a transcript of the whole conversation. One
   sentence of markdown for anything genuinely informative from along the
   way, not a replay of every detour.
2. **Alternate cells**: one markdown cell stating what happens next, one
   code cell that does it.
3. **Execute the code for real first** (a plain script is fine for this
   step), and copy the actual captured stdout/return values into the
   notebook's saved cell outputs. The outputs you save must be what really
   printed — never text you expect it to produce.
4. **Run once with `mode="live"` from an empty `CACHE_DIR`** (see the
   allocation note above before doing this). Then copy that resulting cache
   directory to sit next to the notebook file, and tell the user to commit
   both together if they're versioning this.
5. **If a resource group choice isn't given or obvious, check
   `get_resources`** and pick from that — don't guess a default.
