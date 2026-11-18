# Contributing

This marketplace distributes Claude Code skills and MCP servers for HPC development. Each plugin lives in its own subdirectory and is registered in `.claude-plugin/marketplace.json`.

## Plugin structure

Every plugin follows the same layout:

```
my-plugin/
  skills/
    my-plugin/
      SKILL.md        ← skill instructions and frontmatter
  .mcp.json           ← optional, only for MCP servers
```

The `SKILL.md` frontmatter minimum:

```markdown
---
name: my-plugin
description: What this does and when Claude should use it.
user-invocable: true
---
```

---

## Three patterns

### 1. Pure skill

Just a `SKILL.md`. No server, no installation required. Use this for reference information, workflow guidance, or tool documentation.

Example: [RAPTOR](./raptor/)

```
my-plugin/
  skills/my-plugin/SKILL.md
```

---

### 2. MCP server via Docker

Use this when your tool has native library dependencies or a complex environment. The image is pulled from Docker Hub on first use.

Example: [tadashi](./tadashi/)

```
my-plugin/
  .mcp.json
  skills/my-plugin/SKILL.md   ← recommended but optional
```

`.mcp.json`:
```json
{
  "mcpServers": {
    "my-plugin": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "yourorg/my-plugin:latest"]
    }
  }
}
```

Push your image to Docker Hub before registering the plugin.

---

### 3. MCP server via uvx (PyPI)

Use this when your tool is a pure Python package. `uvx` pulls it from PyPI into an isolated environment on first use — no Docker required.

```
my-plugin/
  .mcp.json
  skills/my-plugin/SKILL.md   ← recommended but optional
```

`.mcp.json`:
```json
{
  "mcpServers": {
    "my-plugin": {
      "command": "uvx",
      "args": ["my-plugin-package"]
    }
  }
}
```

Publish your package to PyPI before registering the plugin.

---

## Registering your plugin

Add an entry to `.claude-plugin/marketplace.json`:

```json
{
  "id": "my-plugin",
  "name": "My Plugin",
  "description": "One sentence shown in the plugin browser.",
  "source": {
    "source": "git-subdir",
    "url": "git@github.com:RIKEN-RCCS/HPC-Agentic-SDK.git",
    "path": "my-plugin"
  }
}
```

Register the same plugin in `.agents/plugins/marketplace.json` and add a row
in `README.md`. Pi and OpenCode use the Codex marketplace paths and each
plugin's `.codex-plugin/plugin.json` to find its skills and MCP servers.
Put stdio launch commands in the plugin's `.mcp.json` so all clients can use
the same configuration.

## Updating HPC Rookery

`rookery/` is a generated, filtered snapshot of upstream HPC Rookery.
The weekly sync opens a pull request after checking that the packaged MCP
servers work with the selected facilities. The upstream commit is recorded
in [rookery/UPSTREAM.json](./rookery/UPSTREAM.json).

To refresh and test the snapshot from an upstream checkout:

```sh
python3 scripts/sync-rookery.py /path/to/hpc-rookery
uv run --isolated --no-project --with ./rookery -- python scripts/check-rookery.py
```

Make changes to Rookery's code or skills upstream. To change the facilities
distributed by the SDK, update the allowlist in `scripts/sync-rookery.py`
and the two marketplace catalogs.
