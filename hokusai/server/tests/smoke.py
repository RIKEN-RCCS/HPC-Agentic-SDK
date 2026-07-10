"""End-to-end smoke test for the HOKUSAI MCP servers over stdio.

    python tests/smoke.py            # read-only: start servers, list tools,
                                     #   search docs, and make live read-only
                                     #   scheduler round trips (get_resources,
                                     #   recent jobs, hostname) — proves the
                                     #   cluster is actually reachable
    python tests/smoke.py --job      # + submit a real tiny job and follow it
                                     #   to completion (needs a working config,
                                     #   SSH access, and a chargeable project)

A passing read-only run is NOT proof the port works (PORTING.md §9): the
job *submit/complete* path is only exercised by --job against a real
cluster. Run --job before considering the port finished.
"""
import argparse
import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def _call(session: ClientSession, name: str, args: dict):
    result = await session.call_tool(name, args)
    text = "\n".join(c.text for c in result.content if getattr(c, "type", "") == "text")
    if result.isError:
        raise RuntimeError(f"{name} errored: {text}")
    return text


async def _connect(module: str):
    params = StdioServerParameters(command=sys.executable, args=["-m", module])
    return stdio_client(params)


async def run_readonly() -> None:
    # Docs server — no SSH needed.
    async with await _connect("hokusai_mcp.docs_server") as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            assert "search_docs" in tools, tools
            print(f"✓ docs server: {len(tools)} tools ({', '.join(sorted(tools))})")
            toc = await _call(session, "list_doc_sections", {})
            print(f"✓ list_doc_sections: {len(toc.splitlines())} sections")

    # HPC server — get_facility reads only bundled config, no SSH.
    async with await _connect("hokusai_mcp.hpc_server") as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            for expected in ("get_facility", "submit_job", "get_job_status",
                             "cancel_job", "fs_ls", "run_command_on_cluster"):
                assert expected in tools, f"missing tool {expected}"
            print(f"✓ hpc server: {len(tools)} tools")
            facility = await _call(session, "get_facility", {})
            assert "HOKUSAI" in facility and "mpc" in facility
            print("✓ get_facility: returned HBW2 facts (static, no SSH)")

            # Live read-only scheduler round trips — these are what actually
            # prove the cluster is reachable (get_facility does not; it only
            # reads bundled JSON). All read-only, so safe to run every time.
            resources = await _call(session, "get_resources", {})
            assert "mpc" in resources, "get_resources should list the mpc partition"
            print(f"✓ get_resources (SSH + sinfo): {resources[:120]!r}")

            recent = await _call(session, "get_job_statuses", {"job_ids": []})
            print(f"✓ get_job_statuses([]) (SSH + sacct): {recent[:120]!r}")

            host = await _call(session, "run_command_on_cluster", {"command": "hostname"})
            print(f"✓ run_command_on_cluster('hostname') (SSH): {host.strip()!r}")
    print("\nRead-only smoke test passed.")


async def run_job() -> None:
    async with await _connect("hokusai_mcp.hpc_server") as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            spec = {
                "name": "hokusai-smoke",
                "executable": "echo hello from HBW2 && hostname && sleep 5",
                "resources": {"node_count": 1, "processes_per_node": 1},
                "attributes": {"duration": "00:05:00", "queue_name": "mpc"},
            }
            preview = await _call(session, "render_job_script", {"spec": spec})
            print("--- rendered script ---\n" + preview + "\n-----------------------")
            out = await _call(session, "submit_job", {"spec": spec})
            print(f"✓ submit_job: {out}")
            import json
            job_id = json.loads(out)["job_id"]
            for _ in range(60):
                status = await _call(session, "get_job_status", {"job_id": job_id})
                print(f"  job {job_id}: {status}")
                if any(s in status for s in ('"completed"', '"failed"', '"canceled"')):
                    break
                await asyncio.sleep(10)
            print("\nJob smoke test finished — confirm the state above is 'completed'.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", action="store_true",
                        help="also submit a real tiny job (needs SSH + a project)")
    args = parser.parse_args()
    asyncio.run(run_readonly())
    if args.job:
        asyncio.run(run_job())
    return 0


if __name__ == "__main__":
    sys.exit(main())
