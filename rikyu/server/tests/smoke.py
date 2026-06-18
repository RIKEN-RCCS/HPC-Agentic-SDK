"""Live smoke test: drive both MCP servers over stdio, exactly as Claude Code does.

Usage:  python tests/smoke.py [--job]

Without --job: docs search + facility/status/queue queries (read-only).
With --job: additionally submits a tiny 5-minute test job via a JobSpec,
polls it to completion, and tails its output.
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
    params = StdioServerParameters(command=str(RUN_SH), args=["rikyu_mcp.docs_server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = [t.name for t in (await session.list_tools()).tools]
            print(f"rikyu-docs tools: {tools}\n")
            await call(session, "search_docs",
                       {"query": "how do I use local scratch storage", "top_k": 2})


async def hpc_checks(submit: bool) -> None:
    params = StdioServerParameters(command=str(RUN_SH), args=["rikyu_mcp.hpc_server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = [t.name for t in (await session.list_tools()).tools]
            print(f"rikyu-hpc tools: {tools}\n")

            await call(session, "get_facility")
            await call(session, "get_resources")
            await call(session, "get_resource", {"resource_id": "ai4s"})
            projects_text = await call(session, "get_projects")
            assert projects_text.strip(), "get_projects returned empty"
            first_project = json.loads(projects_text.strip().split("\n\n")[0])
            await call(session, "get_project", {"project_id": first_project["id"]})
            await call(session, "get_job_statuses", {"job_ids": []})

            # filesystem utilities
            await call(session, "fs_upload",
                       {"path": "/tmp/rikyu-smoke.txt", "content": "smoke test\n"})
            csum1 = await call(session, "fs_checksum", {"path": "/tmp/rikyu-smoke.txt"})
            b64 = await call(session, "fs_download", {"path": "/tmp/rikyu-smoke.txt"})
            import base64
            assert base64.b64decode(b64.strip()).decode() == "smoke test\n", "download content mismatch"
            await call(session, "fs_cp",
                       {"src": "/tmp/rikyu-smoke.txt", "dst": "/tmp/rikyu-smoke-copy.txt"})
            csum2 = await call(session, "fs_checksum", {"path": "/tmp/rikyu-smoke-copy.txt"})
            assert csum1.split()[0] == csum2.split()[0], "checksum mismatch after cp"
            await call(session, "fs_mv",
                       {"src": "/tmp/rikyu-smoke-copy.txt", "dst": "/tmp/rikyu-smoke-moved.txt"})
            csum3 = await call(session, "fs_checksum", {"path": "/tmp/rikyu-smoke-moved.txt"})
            assert csum1.split()[0] == csum3.split()[0], "checksum changed across mv"
            await call(session, "run_command_on_cluster",
                       {"command": "rm -f /tmp/rikyu-smoke.txt /tmp/rikyu-smoke-moved.txt"})

            # chmod / chown / symlink / compress / extract
            await call(session, "fs_upload",
                       {"path": "/tmp/rikyu-fs-test.txt", "content": "hello\n"})
            await call(session, "fs_chmod",
                       {"path": "/tmp/rikyu-fs-test.txt", "mode": "644"})
            await call(session, "fs_symlink",
                       {"path": "/tmp/rikyu-fs-test.txt", "link_path": "/tmp/rikyu-fs-link.txt"})
            await call(session, "fs_compress",
                       {"path": "/tmp/rikyu-fs-test.txt",
                        "target_path": "/tmp/rikyu-fs-test.tar.gz",
                        "compression": "gzip"})
            await call(session, "fs_extract",
                       {"path": "/tmp/rikyu-fs-test.tar.gz",
                        "target_path": "/tmp/rikyu-fs-extracted",
                        "compression": "gzip"})
            await call(session, "run_command_on_cluster",
                       {"command": "rm -rf /tmp/rikyu-fs-test.txt /tmp/rikyu-fs-link.txt "
                                   "/tmp/rikyu-fs-test.tar.gz /tmp/rikyu-fs-extracted"})

            if not submit:
                return

            # container: run a job inside a Singularity image
            container_spec = {
                "name": "rikyu-container-test",
                "executable": "cat /etc/os-release && uname -m",
                "resources": {"node_count": 1, "gpus_per_node": 1},
                "attributes": {"duration": "00:05:00", "queue_name": "1n1gpu"},
                "container": {
                    "image": "$HOME/ubuntu-22.04.sif",
                },
            }
            out_c = await call(session, "submit_job", {"spec": container_spec})
            container_job_id = json.loads(out_c)["job_id"]
            print(f">>> container job {container_job_id}; polling...\n")
            for _ in range(20):
                cjob_text = await call(session, "get_job_status", {"job_id": container_job_id})
                cjob = json.loads(cjob_text)
                if cjob["status"]["state"] in ("completed", "failed", "canceled"):
                    break
                await asyncio.sleep(15)
            assert cjob["status"]["state"] == "completed", \
                f"container job ended {cjob['status']['state']}"
            workdir = cjob["status"]["meta_data"]["workdir"]
            output = await call(session, "fs_tail",
                                {"path": f"{workdir}/slurm-{container_job_id}.out"})
            assert "ubuntu" in output.lower(), f"expected ubuntu in container output: {output}"
            print(">>> container job output confirmed ubuntu inside singularity\n")

            # update_job: submit a job, extend its wall time, then cancel
            spec_hold = {
                "name": "rikyu-update-test",
                "executable": "sleep 300",
                "attributes": {"duration": "00:05:00", "queue_name": "1n1gpu"},
                "resources": {"node_count": 1, "gpus_per_node": 1},
            }
            out_hold = await call(session, "submit_job", {"spec": spec_hold})
            hold_id = json.loads(out_hold)["job_id"]
            await call(session, "update_job",
                       {"job_id": hold_id, "time_limit": "00:10:00", "name": "rikyu-updated"})
            await call(session, "cancel_job", {"job_id": hold_id})

            spec = {
                "name": "rikyu-smoke",
                "executable": "hostname && nvidia-smi -L && echo scratch: $USER_SCRATCH_DIR",
                "attributes": {"duration": "00:05:00", "queue_name": "1n1gpu"},
                "resources": {"node_count": 1, "gpus_per_node": 1},
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
                        help="Also submit and verify a tiny real job.")
    args = parser.parse_args()

    await docs_checks()
    await hpc_checks(submit=args.job)
    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
