"""Live smoke test: drive both MCP servers over stdio, exactly as an agent does.

Usage:  python tests/smoke.py [--job]

Without --job (read-only, safe to run every time): docs search + facility +
**live** scheduler round trips (get_resources -> sinfo, get_job_statuses([]) ->
recent jobs, run_command_on_cluster("hostname")) + a filesystem round trip.
A green read-only run therefore proves the cluster is actually reachable, not
just that tools registered (get_facility alone would touch no SSH).

With --job: additionally submits a tiny CPU job to genoa, exercises update_job
and cancel_job on a throwaway job, polls the real job to completion, and tails
its output — the one check that actually proves job-status logic works.
"""
import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_DIR = Path(__file__).resolve().parent.parent
RUN_SH = str(SERVER_DIR / "run.sh")

REMOTE_DIR = "agent/smoke"  # under ~/agent/, per the visible-directory invariant


async def call(session: ClientSession, tool: str, args: dict | None = None) -> str:
    result = await session.call_tool(tool, args or {})
    text = "\n".join(c.text for c in result.content if c.type == "text")
    status = "ERROR" if result.isError else "ok"
    print(f"--- {tool} [{status}] ---\n{text[:1200]}\n")
    if result.isError:
        raise RuntimeError(f"{tool} failed: {text}")
    return text


async def docs_checks() -> None:
    params = StdioServerParameters(command=RUN_SH, args=["cloud_mcp.docs_server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = [t.name for t in (await session.list_tools()).tools]
            print(f"rccs-cloud-docs tools: {tools}\n")
            await call(session, "search_docs",
                       {"query": "how do I load modules for a partition", "top_k": 2})
            await call(session, "list_doc_sections")


async def hpc_checks(submit: bool) -> None:
    params = StdioServerParameters(command=RUN_SH, args=["cloud_mcp.hpc_server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = [t.name for t in (await session.list_tools()).tools]
            print(f"rccs-cloud-hpc tools: {tools}\n")

            # static
            await call(session, "get_facility")
            # live scheduler round trips — these are what prove reachability
            await call(session, "get_resources")
            await call(session, "get_resource", {"resource_id": "rccs-cloud"})
            await call(session, "get_job_statuses", {"job_ids": []})
            await call(session, "run_command_on_cluster", {"command": "hostname"})

            # filesystem round trip: local file -> remote -> back, verify sha256
            with tempfile.TemporaryDirectory() as tmp:
                src = Path(tmp) / "cloud-smoke.txt"
                src.write_text("smoke test\n")
                remote = f"{REMOTE_DIR}/cloud-smoke.txt"
                up = json.loads(await call(session, "fs_upload",
                                           {"path": remote, "local_path": str(src)}))
                assert up["verified"], "upload sha256 mismatch"
                csum1 = await call(session, "fs_checksum", {"path": remote})
                back = Path(tmp) / "roundtrip.txt"
                dn = json.loads(await call(session, "fs_download",
                                           {"path": remote, "local_path": str(back)}))
                assert dn["verified"] and back.read_text() == "smoke test\n", "download mismatch"
                await call(session, "fs_cp", {"src": remote, "dst": f"{REMOTE_DIR}/copy.txt"})
                csum2 = await call(session, "fs_checksum", {"path": f"{REMOTE_DIR}/copy.txt"})
                assert csum1.split()[0] == csum2.split()[0], "checksum mismatch after cp"
                await call(session, "fs_mv",
                           {"src": f"{REMOTE_DIR}/copy.txt", "dst": f"{REMOTE_DIR}/moved.txt"})
                await call(session, "run_command_on_cluster",
                           {"command": f"rm -rf ~/{REMOTE_DIR}"})

            if not submit:
                return

            # update_job / cancel_job on a throwaway job
            spec_hold = {
                "name": "cloud-update-test",
                "executable": "module load system/genoa mpi/openmpi-x86_64 && sleep 60",
                "attributes": {"duration": "00:05:00", "queue_name": "genoa"},
                "resources": {"node_count": 1},
            }
            hold_id = json.loads(await call(session, "submit_job", {"spec": spec_hold}))["job_id"]
            await call(session, "update_job",
                       {"job_id": hold_id, "time_limit": "00:10:00", "name": "cloud-updated"})
            await call(session, "cancel_job", {"job_id": hold_id})

            # main smoke job: a tiny CPU job on genoa, polled to completion
            spec = {
                "name": "cloud-smoke",
                "executable": "module load system/genoa mpi/openmpi-x86_64 && hostname && uname -m",
                "attributes": {"duration": "00:05:00", "queue_name": "genoa"},
                "resources": {"node_count": 1},
            }
            job_id = json.loads(await call(session, "submit_job", {"spec": spec}))["job_id"]
            print(f">>> submitted job {job_id}; polling...\n")

            # sacct lags sbatch by a second or two on this cluster, so a
            # status query fired immediately after submit can transiently miss
            # the job. Query via get_job_statuses (which returns [] rather than
            # erroring on an unknown id) and tolerate the brief empty window.
            state, job = "unknown", {}
            for _ in range(24):
                await asyncio.sleep(10)
                jobs = json.loads(await call(session, "get_job_statuses", {"job_ids": [job_id]}))
                if not jobs:
                    continue  # not yet visible in sacct
                job = jobs[0]
                state = job["status"]["state"]
                if state in ("completed", "failed", "canceled"):
                    break

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
