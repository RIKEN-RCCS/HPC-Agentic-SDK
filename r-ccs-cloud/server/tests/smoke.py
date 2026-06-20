"""Live smoke test: drive both MCP servers over stdio, exactly as Claude Code does.

Usage:  python tests/smoke.py [--job]

Without --job: docs search + facility/status/queue queries (read-only).
With --job: additionally submits a tiny test job to genoa (CPU), polls it
to completion, and tails its output.
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_DIR = Path(__file__).resolve().parent.parent
RUN_SH = SERVER_DIR / "run.sh"


async def call(session: ClientSession, tool: str, args: dict | None = None) -> str:
    result = await session.call_tool(tool, args or {})
    text = "\n".join(c.text for c in result.content if c.type == "text")
    status = "ERROR" if result.isError else "ok"
    print(f"--- {tool} [{status}] ---\n{text[:1200]}\n")
    if result.isError:
        raise RuntimeError(f"{tool} failed: {text}")
    return text


async def docs_checks() -> None:
    params = StdioServerParameters(command=str(RUN_SH), args=["cloud_mcp.docs_server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = [t.name for t in (await session.list_tools()).tools]
            print(f"rccs-cloud-docs tools: {tools}\n")
            await call(session, "search_docs",
                       {"query": "how do I load modules for a partition", "top_k": 2})
            await call(session, "list_doc_sections")


async def hpc_checks(submit: bool) -> None:
    params = StdioServerParameters(command=str(RUN_SH), args=["cloud_mcp.hpc_server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = [t.name for t in (await session.list_tools()).tools]
            print(f"rccs-cloud-hpc tools: {tools}\n")

            await call(session, "get_facility")
            await call(session, "get_resources")
            await call(session, "get_resource", {"resource_id": "rccs-cloud"})
            await call(session, "get_job_statuses", {"job_ids": []})

            # filesystem utilities
            await call(session, "fs_upload",
                       {"path": "/tmp/cloud-smoke.txt", "content": "smoke test\n"})
            csum1 = await call(session, "fs_checksum", {"path": "/tmp/cloud-smoke.txt"})
            b64 = await call(session, "fs_download", {"path": "/tmp/cloud-smoke.txt"})
            import base64
            assert base64.b64decode(b64.strip()).decode() == "smoke test\n", "download content mismatch"
            await call(session, "fs_cp",
                       {"src": "/tmp/cloud-smoke.txt", "dst": "/tmp/cloud-smoke-copy.txt"})
            csum2 = await call(session, "fs_checksum", {"path": "/tmp/cloud-smoke-copy.txt"})
            assert csum1.split()[0] == csum2.split()[0], "checksum mismatch after cp"
            await call(session, "fs_mv",
                       {"src": "/tmp/cloud-smoke-copy.txt", "dst": "/tmp/cloud-smoke-moved.txt"})
            csum3 = await call(session, "fs_checksum", {"path": "/tmp/cloud-smoke-moved.txt"})
            assert csum1.split()[0] == csum3.split()[0], "checksum changed across mv"
            await call(session, "run_command_on_cluster",
                       {"command": "rm -f /tmp/cloud-smoke.txt /tmp/cloud-smoke-moved.txt"})

            if not submit:
                return

            # update_job: submit a job, extend its wall time, then cancel
            spec_hold = {
                "name": "cloud-update-test",
                "executable": "module load system/genoa mpi/openmpi-x86_64 && hostname",
                "attributes": {"duration": "00:05:00", "queue_name": "genoa"},
                "resources": {"node_count": 1},
            }
            out_hold = await call(session, "submit_job", {"spec": spec_hold})
            hold_id = json.loads(out_hold)["job_id"]
            await call(session, "update_job",
                       {"job_id": hold_id, "time_limit": "00:10:00", "name": "cloud-updated"})
            await call(session, "cancel_job", {"job_id": hold_id})

            # main smoke job: CPU job on genoa
            spec = {
                "name": "cloud-smoke",
                "executable": "module load system/genoa mpi/openmpi-x86_64 && hostname && uname -m",
                "attributes": {"duration": "00:05:00", "queue_name": "genoa"},
                "resources": {"node_count": 1},
            }
            out = await call(session, "submit_job", {"spec": spec})
            job_id = json.loads(out)["job_id"]
            print(f">>> submitted job {job_id}; polling...\n")

            for _ in range(20):
                status_text = await call(session, "get_job_status", {"job_id": job_id})
                job = json.loads(status_text)
                state = job["status"]["state"]
                if state in ("completed", "failed", "canceled"):
                    break
                await asyncio.sleep(15)

            assert state == "completed", f"job ended {state}"
            workdir = job["status"]["meta_data"]["workdir"]
            await call(session, "fs_tail",
                       {"path": f"{workdir}/slurm-{job_id}.out", "lines": 20})


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", action="store_true",
                        help="Also submit and verify a tiny real CPU job on genoa.")
    args = parser.parse_args()

    await docs_checks()
    await hpc_checks(submit=args.job)
    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
