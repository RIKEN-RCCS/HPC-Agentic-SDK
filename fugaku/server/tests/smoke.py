"""Live smoke test for Fugaku MCP servers over stdio.

Usage: python tests/smoke.py [--offline] [--job] [--confirm-billing]

Three tiers per hpc-agent-core's PORTING.md §9: offline (no SSH), read-only
(live but non-consequential), and job (submits a real PJM job and consumes
allocation time — gated behind --confirm-billing).
"""
import argparse
import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from hpc_agent_core.testing import Summary, call, confirm_billing_gate, job_name, payload, run_tier

SERVER_DIR = Path(__file__).resolve().parent.parent
RUN_SH = SERVER_DIR / "run.sh"


async def _docs_session():
    return stdio_client(StdioServerParameters(command=str(RUN_SH), args=["fugaku_mcp.docs_server"]))


async def _hpc_session():
    return stdio_client(StdioServerParameters(command=str(RUN_SH), args=["fugaku_mcp.hpc_server"]))


async def check_docs_server_offline(session: ClientSession) -> None:
    tools = await session.list_tools()
    names = {t.name for t in tools.tools}
    assert "search_docs" in names, f"search_docs missing from fugaku-docs tools: {sorted(names)}"


async def check_docs_server_live(session: ClientSession) -> None:
    result = await call(session, "search_docs", {"query": "layered storage LLIO gfscache", "top_k": 2})
    text = str(payload(result))
    assert text.strip(), "search_docs returned nothing"
    print(f"search_docs -> {text[:300]}")


async def check_hpc_server_offline(session: ClientSession) -> None:
    tools = await session.list_tools()
    names = {t.name for t in tools.tools}
    required = {
        "submit_job", "get_job_status", "get_job_statuses", "update_job", "cancel_job",
        "get_facility", "get_resources", "get_resource", "run_command_on_cluster",
        "fs_ls", "fs_stat", "fs_view", "fs_head", "fs_tail", "fs_mkdir", "fs_upload",
        "fs_download", "fs_checksum", "fs_cp", "fs_mv", "fs_chmod", "fs_chown",
        "fs_symlink", "fs_compress", "fs_extract",
    }
    missing = required - names
    assert not missing, f"missing tools: {sorted(missing)}"

    submit_job_tool = next(t for t in tools.tools if t.name == "submit_job")
    props = (submit_job_tool.input_schema or {}).get("properties", {})
    assert "spec" in props, f"submit_job has no 'spec' parameter: {props}"

    facility = await call(session, "get_facility", {})
    facility_data = payload(facility)
    assert facility_data.get("scheduler", {}).get("submit") == "pjsub", facility_data
    print(f"get_facility -> machine={facility_data.get('machine')!r}")


async def check_hpc_server_live(session: ClientSession) -> None:
    resources = await call(session, "get_resources", {})
    resources_data = payload(resources)
    assert resources_data, "get_resources returned nothing"

    statuses = await call(session, "get_job_statuses", {"job_ids": []})
    payload(statuses)  # just confirm the round trip doesn't error

    whoami = await call(session, "run_command_on_cluster", {"command": "id"})
    whoami_text = str(payload(whoami))
    assert "fugaku" in whoami_text, f"id output didn't mention the fugaku group: {whoami_text}"
    print(f"run_command_on_cluster('id') -> {whoami_text.strip()}")

    ls = await call(session, "fs_ls", {"path": "."})
    assert str(payload(ls)).strip(), "fs_ls returned nothing"


async def check_hpc_server_job(session: ClientSession, group: str) -> None:
    name = job_name("fugaku-smoke")
    spec = {
        "name": name,
        "executable": "hostname && echo PJM_JOBID=$PJM_JOBID",
        "attributes": {"duration": 300, "queue_name": "small", "account": group},
        "resources": {"node_count": 1},
    }
    result = await call(session, "submit_job", {"spec": spec})
    submitted = payload(result)
    job_id = submitted["job_id"]
    print(f">>> submitted job {job_id} ({submitted.get('script_path')}); polling...")

    state = "unknown"
    job = None
    for _ in range(40):
        status = await call(session, "get_job_status", {"job_id": job_id})
        job = payload(status)
        state = job["status"]["state"]
        if state in ("completed", "failed", "canceled"):
            break
        await asyncio.sleep(15)

    assert state == "completed", f"job {job_id} ended in state {state!r}: {job}"

    out_path = f"agent/jobs/{name}.{job_id}.out"
    out = await call(session, "fs_tail", {"path": out_path, "lines": 20})
    out_text = str(payload(out))
    print(f"--- {out_path} ---\n{out_text}")
    assert "PJM_JOBID" in out_text, f"expected job output not found in {out_path}: {out_text}"


async def _run(args: argparse.Namespace) -> Summary:
    summary = Summary()

    async with await _docs_session() as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await run_tier(summary, "docs-offline", check_docs_server_offline(session))

    async with await _hpc_session() as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await run_tier(summary, "hpc-offline", check_hpc_server_offline(session))

    if args.offline or not summary.all_passed:
        summary.skip("read-only", "offline mode or an earlier tier failed")
        summary.skip("job", "offline mode or an earlier tier failed")
        return summary

    async with await _docs_session() as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await run_tier(summary, "docs-read-only", check_docs_server_live(session))

    async with await _hpc_session() as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await run_tier(summary, "hpc-read-only", check_hpc_server_live(session))

    if not args.job:
        summary.skip("job", "--job not given")
        return summary
    if not summary.all_passed:
        summary.skip("job", "an earlier tier failed")
        return summary

    from fugaku_mcp import config
    group = config.default_group()
    if not group:
        summary.skip("job", "no defaults.group configured (FUGAKU_GROUP or ~/.hpc-agent/fugaku.json)")
        return summary

    async with await _hpc_session() as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await run_tier(summary, "job", check_hpc_server_job(session, group))

    return summary


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Only run the offline tier (no SSH).")
    parser.add_argument("--job", action="store_true", help="Also submit and verify a real tiny PJM job.")
    parser.add_argument("--confirm-billing", action="store_true", help="Required alongside --job.")
    args = parser.parse_args()

    refusal = confirm_billing_gate(
        args, reason="A --job run submits a real pjsub job on the 'small' resource "
                      "group and consumes allocation time on your project group."
    )
    if refusal:
        print(refusal, file=sys.stderr)
        return 1

    summary = await _run(args)
    print(summary.line())
    return 0 if summary.all_passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
