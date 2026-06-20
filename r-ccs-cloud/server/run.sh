#!/bin/bash
# Launch an MCP server module from the cloud_mcp package.
# Usage: run.sh <module>   e.g. run.sh cloud_mcp.hpc_server
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE="$1"
shift || true

if command -v uv >/dev/null 2>&1; then
    exec uv run --quiet --directory "$DIR" python -m "$MODULE" "$@"
fi

VENV="$DIR/.venv"
if [ ! -x "$VENV/bin/python" ]; then
    python3 -m venv "$VENV" >&2
    "$VENV/bin/pip" install --quiet --upgrade pip >&2
fi
if ! "$VENV/bin/python" -c "import cloud_mcp, mcp, remotemanager" >/dev/null 2>&1; then
    "$VENV/bin/pip" install --quiet -e "$DIR" >&2
fi

exec "$VENV/bin/python" -m "$MODULE" "$@"
