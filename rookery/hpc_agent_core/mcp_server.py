"""The one place that imports the MCP SDK's server class.

Every machine repo imports MCPServer from here, never from `mcp` directly,
and none of them declare "mcp" as their own dependency — only hpc-agent-core
does. mcp 2.0.0 renamed mcp.server.fastmcp.FastMCP to
mcp.server.mcpserver.MCPServer with no deprecation window, which broke every
consumer overnight because each one imported it independently and pinned (or
didn't) the SDK on its own. If the SDK's API surface moves again, this file
is the only one that needs to change.

The subclass below exists because pydantic emits tool schemas with local
``$ref``/``$defs`` indirection (``spec: {"$ref": "#/$defs/JobSpec"}``), and
some model gateways cannot parse that shape: they see an opaque ref where a
plain object should be, and emit the parameter as a JSON-encoded *string* —
which harness-side schema validation then rejects before the call ever
reaches this server (the server itself would have accepted either form).
Pi hit the same failure class on its Anthropic side (pi #9557) for the same
reason. Inlining the definitions at list_tools time removes the trigger for
every client at once. Call-time validation is untouched: pydantic still
builds arguments from the function signature, not from this published
schema, so accepting a call never depends on the inlining.
"""
from typing import Any

from mcp.server.mcpserver import MCPServer as _SdkMCPServer
from mcp.types import Tool as MCPTool

__all__ = ["MCPServer"]


class _Unresolvable(Exception):
    """A local $ref that cannot be safely inlined (missing, or a cycle)."""


def _inline_local_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Return ``schema`` with local ``$ref`` entries replaced by their
    definitions, or ``schema`` unchanged when any ref cannot be resolved.

    All-or-nothing on purpose: a schema is either fully inlined or served
    exactly as generated, never a half-expanded hybrid. Non-local refs
    (URLs) and unusual JSON pointers raise ``_Unresolvable`` and so also
    take the unchanged fallback.
    """
    defs: dict[str, Any] = {}
    for key in ("$defs", "definitions"):
        value = schema.get(key)
        if isinstance(value, dict):
            defs.update(value)
    if not defs:
        return schema

    def expand(node: Any, expanding: frozenset[str]) -> Any:
        if isinstance(node, list):
            return [expand(item, expanding) for item in node]
        if not isinstance(node, dict):
            return node
        ref = node.get("$ref")
        if not isinstance(ref, str) or not ref.startswith("#/"):
            return {key: expand(value, expanding) for key, value in node.items()}
        name = ref.rsplit("/", 1)[-1]  # "#/$defs/JobSpec" -> "JobSpec"
        if name in expanding or name not in defs:
            raise _Unresolvable(ref)
        merged = dict(expand(defs[name], expanding | {name}))
        # JSON Schema allows keywords alongside $ref; the caller's win.
        for key, value in node.items():
            if key != "$ref":
                merged[key] = value
        return merged

    try:
        return {
            key: expand(value, frozenset())
            for key, value in schema.items()
            if key not in ("$defs", "definitions")
        }
    except _Unresolvable:
        return schema


class MCPServer(_SdkMCPServer):
    """The SDK server, publishing tool schemas with local $refs inlined.

    list_tools is the single point where schemas reach a client, so the
    inlining cannot drift from what a call later accepts.
    """

    async def list_tools(self) -> list[MCPTool]:
        tools = await super().list_tools()
        inlined = []
        for tool in tools:
            update: dict[str, Any] = {"input_schema": _inline_local_refs(tool.input_schema)}
            if tool.output_schema is not None:
                update["output_schema"] = _inline_local_refs(tool.output_schema)
            inlined.append(tool.model_copy(update=update))
        return inlined
