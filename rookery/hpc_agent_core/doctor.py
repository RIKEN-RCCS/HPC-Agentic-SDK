"""Generic health checks for the unified multi-facility MCP server.

Checks the config file, SSH access to the cluster, scheduler availability,
the embedding endpoint, and the docs index — for every registered facility
by default (call with a single `facility` slug to check just one). Exits
nonzero if a required check fails for any facility checked (the embedding
endpoint is optional — docs search falls back to BM25; a missing/malformed
config file is a WARN, not a FAIL, per the "never fail to start" invariant
— see PORTING.md).

server/hpc_mcp/doctor.py is the entry point:

    from hpc_mcp import facilities_loaded  # noqa: F401 -- registers every facility
    from hpc_agent_core.doctor import main

    if __name__ == "__main__":
        import sys
        sys.exit(main())

The scheduler check is delegated to each facility's own backend via
SchedulerBackend.check_scheduler(), so a non-Slurm facility needs no change
here: SlurmBackend uses a `sinfo --version` probe, PJMBackend checks its
commands are on PATH (PJM has no version flag on anything). This is not
cosmetic — an earlier hardcoded `sinfo --version` reported "slurm" as
Fugaku's scheduler, because a Fugaku login node has Slurm installed for
unrelated pre/post-processing work. The probe succeeded and the answer was
wrong.
"""
import json
import subprocess
import sys

from hpc_agent_core import config

OK, WARN, FAIL = "✓", "!", "✗"

_SSH_DISABLED = frozenset({"", "no", "false", "off", "none", "0"})
_SSH_CONTROL_MASTERS = frozenset({"yes", "auto", "ask", "autoask"})


def _ssh_config(host: str) -> dict[str, str] | None:
    """Return OpenSSH's resolved settings for ``host``, without connecting.

    ``ssh -G`` applies the user's normal SSH configuration but does not open
    a network connection. It is therefore the right authority for transport
    settings such as ControlMaster: parsing ~/.ssh/config ourselves would
    miss Include files, Match blocks, and system-wide configuration.
    """
    try:
        result = subprocess.run(
            ["ssh", "-G", host], capture_output=True, text=True,
            timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"{WARN} ssh multiplexing: could not inspect local SSH config: {exc}")
        return None
    if result.returncode:
        detail = (result.stderr or result.stdout or "").strip()
        print(f"{WARN} ssh multiplexing: ssh -G failed for {host!r}: {detail}")
        return None
    return {
        key: value
        for line in result.stdout.splitlines()
        if (parts := line.split(None, 1)) and len(parts) == 2
        for key, value in [parts]
    }


def check_ssh_multiplexing(facility: str) -> bool:
    """Report whether repeated SSH calls can reuse an OpenSSH master.

    This is advisory: a facility remains usable without multiplexing, and a
    user may deliberately opt out with ``ControlMaster no``. The check is
    local-only: neither ``ssh -G`` nor ``ssh -O check`` authenticates to or
    opens a fresh connection to the cluster.
    """
    from hpc_agent_core.middleware import is_local_host

    host = config.ssh_host(facility)
    if is_local_host(host):
        print(f"{OK} ssh multiplexing: not applicable (local host {host})")
        return True

    settings = _ssh_config(host)
    if settings is None:
        return True
    master = settings.get("controlmaster", "").lower()
    control_path = settings.get("controlpath", "").lower()
    persist = settings.get("controlpersist", "").lower()

    if master in _SSH_DISABLED:
        print(f"{WARN} ssh multiplexing: explicitly disabled by ControlMaster {master or 'no'}")
        return True
    if master not in _SSH_CONTROL_MASTERS or control_path in _SSH_DISABLED:
        print(
            f"{WARN} ssh multiplexing: not configured; repeated cluster calls "
            "will open new SSH connections. Use the configuring skill to add "
            "ControlMaster auto, ControlPath, and ControlPersist."
        )
        return True
    if persist in _SSH_DISABLED:
        print(
            f"{WARN} ssh multiplexing: ControlPersist is disabled; a master "
            "will not remain available between calls. Set ControlPersist 30m."
        )

    try:
        result = subprocess.run(
            ["ssh", "-O", "check", host], capture_output=True, text=True,
            timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"{WARN} ssh multiplexing: could not check master socket: {exc}")
        return True
    if result.returncode == 0:
        print(f"{OK} ssh multiplexing: active for {host}")
    else:
        print(
            f"{WARN} ssh multiplexing: configured but no active master for "
            f"{host}. Start one interactively with: ssh -MNf {host}"
        )
    return True


def check_config_file(facility: str) -> bool:
    fac = config.get_facility(facility)
    path = config.config_path(fac)
    if not path.exists():
        print(f"{WARN} config file: {path} not found (using env vars / "
              f"defaults — the {fac.slug}-configuring skill can create it)")
        return True
    try:
        config.file_config(facility)
    except RuntimeError as e:
        print(f"{FAIL} config file: {e}")
        return False
    print(f"{OK} config file: {path}")
    return True


def check_ssh_scheduler_probe(facility: str, probe: str, name: str) -> bool:
    """Run a scheduler probe whose output starts with the scheduler's name.

    Fits Slurm (`sinfo --version` -> "slurm 24.05"). Schedulers with no
    version flag use check_commands_on_path() instead — see
    SchedulerBackend.check_scheduler(), which is what doctor actually calls.
    """
    from hpc_agent_core.middleware import run_command
    out = run_command(facility, probe)
    if out.strip().lower().startswith(name.lower()):
        print(f"{OK} {name}: {out.strip()}")
        return True
    print(f"{FAIL} {name}: {out.strip()[:200]}")
    return False


def check_ssh(facility: str, ok_token: str, scheduler_probe: str = "", scheduler_name: str = "") -> bool:
    from hpc_agent_core.middleware import is_local_host, run_command
    host = config.ssh_host(facility)
    # "ssh (host): connected" would be misleading when host is localhost/
    # 127.* — remotemanager routes that case to a bare local shell with no
    # ssh subprocess at all (see middleware.get_frontend()'s docstring).
    label = f"local ({host})" if is_local_host(host) else f"ssh ({host})"
    try:
        output = run_command(facility, f"echo {ok_token} && hostname")
    except Exception as e:
        print(f"{FAIL} {label}: {e}")
        return False
    if ok_token not in output:
        print(f"{FAIL} {label}: unexpected response: {output[:200]}")
        return False
    print(f"{OK} {label}: connected to {output.strip().splitlines()[-1]}")
    if scheduler_probe:      # legacy direct callers; doctor uses the backend
        return check_ssh_scheduler_probe(facility, scheduler_probe, scheduler_name)
    return True


def check_commands_on_path(facility: str, names, label: str) -> bool:
    """Verify each of `names` resolves via `command -v` on `facility`'s
    cluster.

    For schedulers with no single --version-style probe command —
    check_ssh()'s scheduler_probe/scheduler_name assumes one command whose
    output starts with the scheduler's name (fine for Slurm's
    `sinfo --version`), which doesn't fit a scheduler that only offers
    several must-exist commands and no version flag at all (PJM's
    pjsub/pjstat/pjdel/pjalter, Bridge's ccc_msub/ccc_mprun/ccc_mpp/
    ccc_mpinfo). Call this alongside your own SSH connectivity check
    (a few lines — see check_ssh()'s source for the echo/hostname pattern)
    rather than through check_ssh() itself.

    Checked one at a time: `command -v` exits non-zero for a single missing
    command, and middleware.run_command always raises on non-zero exit — a
    single combined "command -v a b c" would raise (and lose which ones
    were actually found) the moment any one is missing.
    """
    from hpc_agent_core.middleware import run_command
    missing = []
    for cmd in sorted(names):
        try:
            run_command(facility, f"command -v {cmd}")
        except RuntimeError:
            missing.append(cmd)
    if missing:
        print(f"{FAIL} {label}: missing {', '.join(missing)}")
        return False
    print(f"{OK} {label}: {', '.join(sorted(names))}")
    return True


def check_embedding(facility: str) -> bool:
    """Probe the embedding endpoint, or report a WARN if the facility has no
    shared endpoint configured at all (not every facility has one — a
    facility that never registers embed_base_url/embed_model with real
    values is BM25-only by design, which is fine, not a failure). A
    configured endpoint that merely lacks/rejects an API key still attempts
    the connection and reports FAIL, since that's a real signal (e.g. a 401)
    worth surfacing, unlike "no endpoint decided for this facility" which
    isn't an error to fix.
    """
    fac = config.get_facility(facility)
    if not (fac.embed_base_url and fac.embed_model):
        print(f"{WARN} embedding: not configured for this facility; docs search uses BM25 keyword matching")
        return True
    from hpc_agent_core.rag.embed import get_client
    client = get_client(fac)
    try:
        vector = client.embed(["connectivity probe"])[0]
    except Exception as e:
        print(f"{FAIL} embedding ({fac.embed_model} @ {fac.embed_base_url}): {e}")
        return False
    print(f"{OK} embedding: {fac.embed_model} @ {fac.embed_base_url} (dim {len(vector)})")
    return True


def check_docs_guide_bundled(facility: str) -> bool:
    """Verify the guide markdown actually ships under data_dir — catches a
    missing/misnamed guide file before a user hits it as a confusing empty
    docs index."""
    path = config.docs_source(facility)
    if not path.exists():
        print(f"{FAIL} guide file: {path} missing")
        return False
    print(f"{OK} guide file: {path}")
    return True


def check_docs_index(facility: str) -> bool:
    index_dir = config.docs_index_dir(facility)
    chunks_path = index_dir / "chunks.json"
    if not chunks_path.exists():
        print(f"{FAIL} docs index: {chunks_path} missing — run: "
              f"python -m hpc_agent_core.rag.ingest {facility}")
        return False
    with open(chunks_path) as f:
        n_chunks = len(json.load(f))
    emb_path = index_dir / "embeddings.npy"
    if not emb_path.exists():
        print(f"{OK} docs index: {n_chunks} chunks (no embeddings — BM25 only; "
              f"run: python -m hpc_agent_core.rag.ingest {facility})")
        return True
    import numpy as np
    n_vectors = np.load(emb_path).shape[0]
    if n_vectors != n_chunks:
        print(f"{FAIL} docs index: {n_chunks} chunks but {n_vectors} embeddings — "
              f"rebuild with: python -m hpc_agent_core.rag.ingest {facility}")
        return False
    print(f"{OK} docs index: {n_chunks} chunks with embeddings")
    return True


def check_facility(facility: str) -> bool:
    """Run every check for one facility; return True iff all passed.

    The scheduler check is delegated to that facility's own backend
    (SchedulerBackend.check_scheduler), because schedulers differ in how
    they can even be probed — and because a hardcoded `sinfo --version`
    once reported "slurm" as Fugaku's scheduler, which is PJM. A Fugaku
    login node happens to have Slurm installed for unrelated pre/post
    work, so the probe succeeded and said something false.
    """
    from facilities.registry import get_backend
    fac = config.get_facility(facility)
    print(f"\n=== {fac.slug} ({fac.display_name}) ===")
    ok_token = f"{fac.slug}-doctor-ok"
    ssh_ok = check_ssh(facility, ok_token)
    results = [
        check_config_file(facility),
        check_ssh_multiplexing(facility),
        ssh_ok,
        get_backend(facility).check_scheduler() if ssh_ok else False,
        check_docs_guide_bundled(facility),
        check_docs_index(facility),
        check_embedding(facility),
    ]
    return all(results)


def main(facility: str | None = None) -> int:
    """Check one facility (if `facility` is given) or every registered
    facility (the default)."""
    import hpc_mcp
    if hpc_mcp.FAILED_FACILITIES and not facility:
        print("\n=== facilities that failed to load ===")
        for slug, error in hpc_mcp.FAILED_FACILITIES.items():
            print(f"{FAIL} {slug}: {error}")

    facilities = [config.get_facility(facility)] if facility else config.list_facilities()
    if not facilities:
        print(f"{FAIL} no facilities registered")
        return 1
    results = {fac.slug: check_facility(fac.slug) for fac in facilities}
    print()
    for slug, ok in results.items():
        print(f"{OK if ok else FAIL} {slug}")
    if all(results.values()) and not hpc_mcp.FAILED_FACILITIES:
        print("\nAll checks passed.")
        return 0
    print("\nSome checks FAILED — see above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
