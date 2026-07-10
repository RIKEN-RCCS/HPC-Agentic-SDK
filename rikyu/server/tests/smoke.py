"""Read-only MCP stdio smoke test for the RIKYU plugin — see PORTING.md §9.

    python tests/smoke.py          # read-only: tool registration, docs
                                    # search, get_facility, an SSH round
                                    # trip via get_job_statuses([]) and
                                    # run_command_on_cluster('hostname')
    python tests/smoke.py --job    # + submits a real 1-GPU job and prints
                                    # its job ID (does not wait for it to
                                    # finish or clean it up — check on it
                                    # and scancel/let it run to completion
                                    # yourself)

A passing run here (and a passing `python -m rikyu_mcp.doctor`) is not
proof the port works end to end — see PORTING.md §9's warning. Run with
--job at least once, with real RIKYU SSH access configured
(~/.hpc-agent/rikyu.json or RIKYU_HOST), before considering this port done.
"""
import argparse
import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_REQUIRED_HPC_TOOLS = {
    "get_facility", "get_resources", "get_resource", "get_drained_nodes",
    "submit_job", "get_job_status", "get_job_statuses", "cancel_job", "update_job",
    "run_command_on_cluster",
    "fs_ls", "fs_stat", "fs_view", "fs_head", "fs_tail", "fs_mkdir",
    "fs_upload", "fs_download", "fs_checksum", "fs_cp", "fs_mv",
    "fs_chmod", "fs_chown", "fs_symlink", "fs_compress", "fs_extract",
}
_REQUIRED_DOCS_TOOLS = {"search_docs", "list_doc_sections", "read_doc_section"}


def _text(result) -> str:
    return result.content[0].text if result.content else ""


async def check_docs_server() -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "rikyu_mcp.docs_server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            missing = _REQUIRED_DOCS_TOOLS - names
            assert not missing, f"docs server missing tools: {missing}"

            sections = await session.call_tool("list_doc_sections", {})
            assert _text(sections).strip(), "list_doc_sections returned nothing — was the docs index built?"
            print(f"[docs] list_doc_sections: {len(_text(sections).splitlines())} sections")

            results = await session.call_tool("search_docs", {"query": "gpu request slurm partition", "top_k": 2})
            assert _text(results).strip(), "search_docs returned nothing"
            print("[docs] search_docs: OK")


async def check_hpc_server(submit_job: bool) -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "rikyu_mcp.hpc_server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            missing = _REQUIRED_HPC_TOOLS - names
            assert not missing, f"hpc server missing tools: {missing}"
            print(f"[hpc] {len(names)} tools registered")

            facility = await session.call_tool("get_facility", {})
            assert _text(facility).strip(), "get_facility returned nothing"
            print("[hpc] get_facility: OK (no SSH required)")

            # get_resources is a live sinfo query (not static config), so
            # this is the first real SSH round trip in this test, despite
            # being grouped with the facility checks above.
            resources = await session.call_tool("get_resources", {})
            assert "gpu" in _text(resources), "get_resources should list the 'gpu' partition"
            print(f"[hpc] get_resources (SSH + sinfo): {_text(resources)[:200]!r}")

            # First real SSH round trips: recent-jobs query and a harmless
            # login-node command.
            statuses = await session.call_tool("get_job_statuses", {"job_ids": []})
            print(f"[hpc] get_job_statuses([]) (SSH + sacct): {_text(statuses)[:200]!r}")

            hostname = await session.call_tool("run_command_on_cluster", {"command": "hostname"})
            print(f"[hpc] run_command_on_cluster('hostname') (SSH): {_text(hostname).strip()!r}")

            if submit_job:
                spec = {
                    "name": "rikyu-smoke-test",
                    "executable": "nvidia-smi",
                    "resources": {"gpus": 1},
                    "attributes": {"duration": "00:05:00"},
                }
                submitted = await session.call_tool("submit_job", {"spec": spec})
                print(f"[hpc] submit_job: {_text(submitted)}")
                print("[hpc] NOTE: this job is now queued/running on RIKYU — check its "
                      "status and cancel it yourself if you don't want it to run to completion.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--job", action="store_true",
                         help="Also submit a real 1-GPU job (nvidia-smi, 5 min wall time).")
    args = parser.parse_args()

    asyncio.run(check_docs_server())
    asyncio.run(check_hpc_server(submit_job=args.job))
    print("\nAll smoke checks passed.")


if __name__ == "__main__":
    main()
