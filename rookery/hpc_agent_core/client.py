"""Public, script/notebook-facing MCP client for the HPC agent family.

Unlike `hpc_agent_core.testing` (asserts, pass/fail tiers — for
`tests/smoke.py` only), everything here is meant to be imported directly by
code that wants to drive a machine's tool surface *without* an interactive
agent session behind it: a notebook distilling exploratory agent work into a
reproducible narrative, a one-off script, CI.

`connect()` opens an MCP stdio session against a machine's `hpc_server` (or
`docs_server`) executable — either a dev-mode `python -m` invocation
(`dev_params`) or the same pinned `uv tool run --from git+...@<ref>`
invocation a plugin's own `.mcp.json` uses (`pinned_params`), pinning a tag
or commit rather than `main` for reproducibility across time — and hands
back an `HpcClient` that exposes every registered tool as a plain async
method (`await hpc.submit_job(spec)` instead of
`payload(await call(session, "submit_job", {...}))`).

Optional on-disk caching (`mode="lazy"` / `"replay"`) lets a notebook be
re-run without re-hitting the cluster: results are cached per (tool name,
canonicalized args). `wait_for_job` is special-cased — polling calls the
same status tool with the same job_id and gets *different* answers over
time on purpose, so only its terminal result is ever cached, never an
intermediate poll (see its docstring for why a generic per-call cache would
get this wrong).

`connect()` is async (`async with connect(...) as hpc: await hpc.submit_job(...)`).
Most of the time `connect_sync()` is what you actually want in a notebook or
script: same `HpcClient` underneath, but every call blocks instead of needing
`await`, and there's no `async with`/`__aenter__` ceremony spread across
cells — `hpc = connect_sync(...)`, `hpc.submit_job(...)`, `hpc.close()`.

Three modes, set once on `connect()`/`connect_sync()`:
  - "live":   always call the real server; still writes to the cache as a
              side effect, so a live run recharges it for next time.
  - "lazy":   use the cache if present, else fall back to live and cache
              the result. The default — good for iterating on a notebook's
              later cells without resubmitting jobs on every "run all".
  - "replay": cache-only, raises CacheMiss on anything not already
              recorded. No SSH is attempted at all. This is the mode to
              hand a notebook to someone with no cluster account: "run
              all" reproduces the recorded narrative in seconds, offline.

A cache-backed "lazy" run is not proof a notebook still reproduces
end-to-end — a stale cache happily papers over a since-broken call. Run
"live" at least once before trusting a notebook as a validated artifact,
the same way a machine repo's read-only/job smoke tiers (not just its
offline tier) are what actually prove a port works end to end — see
PORTING.md §9.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import json
import shutil
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

Mode = Literal["live", "lazy", "replay"]

# JobState values (hpc_agent_core.models.JobState) that end wait_for_job's
# polling loop. Duplicated as plain strings rather than importing JobState
# to keep this module import-light; kept in sync by hand — small, stable enum.
_TERMINAL_STATES = {"completed", "failed", "canceled"}


def _extract_state(status: Any) -> Any:
    """Pull the JobState string out of a get_job_status result. The shared
    `Job` model (hpc_agent_core.models) nests it as `status.status.state`;
    tolerate a flatter `{"state": ...}` shape too in case a future/odd tool
    returns one, rather than hard-failing on the one shape every current
    machine repo actually uses.
    """
    if not isinstance(status, dict):
        return status
    nested = status.get("status")
    if isinstance(nested, dict) and "state" in nested:
        return nested["state"]
    return status.get("state")


def dev_params(package: str, module: str, *, env: dict[str, str] | None = None) -> StdioServerParameters:
    """StdioServerParameters for a dev-mode server: `python -m <package>.<module>`,
    run against whatever this interpreter resolves (an editable checkout,
    typically). Matches the pattern every machine repo's `tests/smoke.py`
    already uses, e.g. `dev_params("rikyu_mcp", "hpc_server")`.
    """
    return StdioServerParameters(command=sys.executable, args=["-m", f"{package}.{module}"], env=env)


def pinned_params(
    remote: str,
    script: str,
    *,
    ref: str = "main",
    subdirectory: str | None = None,
    env: dict[str, str] | None = None,
) -> StdioServerParameters:
    """StdioServerParameters for a pinned-release server, launched exactly the
    way a plugin's own `.mcp.json` launches it:
    `uv tool run --quiet --from git+<remote>@<ref> <script>`. Pass
    ``subdirectory="server"`` for older repositories whose Python project
    lives below the repository root.

    `remote` is the git remote URL; `script` is the console-script entry
    point. Pin `ref` to a tag or commit, not `main` — a reproduction
    notebook meant to still work in six months shouldn't silently pick up
    whatever `main` has become by then. For example, an older per-machine
    repository such as RIKEN-RCCS/Rikyu-Agent also needs
    ``subdirectory="server"`` because its pyproject.toml is not at the root.
    """
    source = f"git+{remote}@{ref}"
    if subdirectory:
        source += f"#subdirectory={subdirectory}"
    return StdioServerParameters(
        command="uv",
        args=[
            "tool", "run", "--quiet", "--from",
            source, script,
        ],
        env=env,
    )


class CacheMiss(RuntimeError):
    """Raised in "replay" mode when a call has no recorded result."""


class Cache:
    """Content-addressed, one-JSON-file-per-call cache. Keyed on (tool name,
    canonicalized kwargs), so re-running a notebook cell with the same
    arguments is a cache hit and changing an argument is a fresh key, never
    a stale hit. Files are plain and diffable on purpose — meant to be
    read, and optionally committed alongside the notebook so a "replay" run
    needs no cluster access at all.
    """

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str, kwargs: dict) -> Path:
        canonical = json.dumps(kwargs, sort_keys=True, default=str)
        digest = hashlib.sha256(f"{name}:{canonical}".encode()).hexdigest()[:16]
        return self.directory / f"{name}-{digest}.json"

    def has(self, name: str, kwargs: dict) -> bool:
        return self._path(name, kwargs).exists()

    def get(self, name: str, kwargs: dict) -> Any:
        return json.loads(self._path(name, kwargs).read_text())["result"]

    def put(self, name: str, kwargs: dict, result: Any) -> None:
        path = self._path(name, kwargs)
        path.write_text(
            json.dumps({"tool": name, "args": kwargs, "result": result}, indent=2, default=str)
        )

    def _blob_path(self, name: str, kwargs: dict) -> Path:
        return self._path(name, kwargs).with_suffix(".blob")

    def has_blob(self, name: str, kwargs: dict) -> bool:
        return self._blob_path(name, kwargs).exists()

    def put_blob(self, name: str, kwargs: dict, source_path: str | Path) -> None:
        """Copy an actual file's bytes into the cache, alongside its JSON
        metadata entry. Only `fs_download` uses this — see its docstring on
        `HpcClient` for why a metadata-only cache isn't enough for it.
        """
        shutil.copyfile(source_path, self._blob_path(name, kwargs))

    def get_blob(self, name: str, kwargs: dict) -> Path:
        return self._blob_path(name, kwargs)


async def call(session: ClientSession, name: str, args: dict | None = None):
    """Call a tool and raise if it errored, with the server's own error text
    folded into the exception so the failure is diagnosable from the
    caller's own output, not a separate log line.
    """
    result = await session.call_tool(name, args or {})
    if result.is_error:
        detail = "".join(getattr(block, "text", "") for block in result.content)
        raise AssertionError(f"{name} failed: {detail or '(server returned no error detail)'}")
    return result


def payload(result):
    """Return a tool result's actual value.

    Prefers `structured_content`; only falls back to the joined content-block
    text when it's absent. Non-object return types (e.g. `list[dict]`) are
    wire-wrapped as `{"result": ...}`; unwrapped here so an empty list reads
    as an empty list rather than a truthy one-key dict.

    `structured_content` is absent specifically for a bare, unparameterized
    `dict` return annotation (e.g. `def get_facility() -> dict`) — the MCP
    surface can't derive an output schema for it, unlike `list[dict]` (whose
    array-of-object shape it can schema, and which *does* arrive via
    structured_content already). For that fallback case, the joined text is
    itself the tool's JSON serialization (verified against a real mcp 2.0.0
    server), so it's parsed here rather than every call site needing its own
    `json.loads` wrapper. Only promoted to the parsed value when the parse
    succeeds *and* yields a dict/list — a scalar-looking result (a bare
    number, "true", "null") stays a string, so plain command output that
    happens to look numeric (e.g. an echoed job ID) isn't silently coerced
    into an int and quietly loses things like trailing whitespace a caller
    might still care about.
    """
    value = result.structured_content
    if value is not None:
        if isinstance(value, dict) and value.keys() == {"result"}:
            return value["result"]
        return value
    text = "".join(getattr(block, "text", "") for block in result.content)
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text
    return parsed if isinstance(parsed, (dict, list)) else text


class HpcClient:
    """Wraps a live `ClientSession`, exposing every registered tool as a
    plain async method with optional caching. Not constructed directly —
    use `connect()`.
    """

    def __init__(self, session: ClientSession, *, mode: Mode = "lazy", cache: Cache | None = None) -> None:
        self._session = session
        self._mode = mode
        self._cache = cache

    @property
    def session(self) -> ClientSession:
        """Escape hatch: the raw ClientSession, for anything this wrapper
        doesn't cover (e.g. `list_tools()`)."""
        return self._session

    async def _call(self, name: str, kwargs: dict) -> Any:
        if self._cache is not None and self._mode != "live":
            if self._cache.has(name, kwargs):
                return self._cache.get(name, kwargs)
            if self._mode == "replay":
                raise CacheMiss(
                    f"No cached result for {name}({kwargs}) and mode is 'replay' — "
                    "no cluster connection is attempted in this mode. Re-run with "
                    "mode='lazy' or 'live' once to record it."
                )
        result = payload(await call(self._session, name, kwargs))
        if self._cache is not None and self._mode != "replay":
            self._cache.put(name, kwargs, result)
        return result

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)

        async def method(**kwargs: Any) -> Any:
            return await self._call(name, kwargs)

        return method

    async def fs_download(self, remote_path: str, local_path: str, **kwargs: Any) -> Any:
        """Download `remote_path` to `local_path`.

        Overridden rather than left to the generic `__getattr__` path
        because the generic cache only stores a call's *return value*
        (checksum, byte count, ...), not the file's actual bytes. That's
        fine for most tools, but `fs_download`'s whole point is producing a
        local artifact that later cells (analysis, plotting) read off
        disk — a metadata-only cache hit in "replay" mode would happily
        return `{"verified": true, ...}` while `local_path` silently never
        gets written, which breaks the very first cell that tries to open
        it on a fresh clone with no prior live run. So the actual bytes are
        copied into the cache directory too, alongside the JSON metadata,
        and a cache hit here means "materialize the real file", not just
        "return the same dict as last time".

        `local_path` is deliberately excluded from the cache key — it's a
        destination for *this* call, not part of what identifies the
        content being fetched (`remote_path` + any other kwargs are). Downloading
        the same remote file to a different local path on a later run is
        still a cache hit, materialized at the new location; the returned
        metadata's `local_path` is updated to match rather than echoing
        wherever the recording run happened to put it.
        """
        key = {"remote_path": remote_path, **kwargs}
        if self._cache is not None and self._mode != "live":
            if self._cache.has("fs_download", key) and self._cache.has_blob("fs_download", key):
                Path(local_path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(self._cache.get_blob("fs_download", key), local_path)
                cached_result = self._cache.get("fs_download", key)
                if isinstance(cached_result, dict):
                    cached_result = {**cached_result, "local_path": local_path}
                return cached_result
            if self._mode == "replay":
                raise CacheMiss(
                    f"No cached file for fs_download({remote_path!r}) and mode is 'replay'. "
                    "Re-run with mode='lazy' or 'live' once to record it."
                )
        result = payload(
            await call(
                self._session, "fs_download",
                {"remote_path": remote_path, "local_path": local_path, **kwargs},
            )
        )
        if self._cache is not None and self._mode != "replay":
            self._cache.put("fs_download", key, result)
            self._cache.put_blob("fs_download", key, local_path)
        return result

    async def wait_for_job(
        self,
        job_id: str,
        *,
        status_tool: str = "get_job_status",
        poll_interval: float = 15.0,
        timeout: float = 3600.0,
        **extra_kwargs: Any,
    ) -> Any:
        """Block until `job_id` reaches a terminal JobState, polling
        `status_tool` every `poll_interval` seconds; return that terminal
        status.

        `extra_kwargs` are merged into every status_tool call alongside
        job_id and included in the cache key — e.g. a unified multi-facility
        server's `wait_for_job(job_id, facility="rikyu")`.

        Deliberately not just "call `status_tool` through the generic
        per-call cache": polling calls the same tool with the same job_id
        and gets *different* answers over time (queued -> active ->
        completed) by design, so a naive cache would memoize whatever
        transient state happened to be live when it was first recorded and
        return that forever after. Only the terminal result is cached here,
        under a `("wait_for_job", {"job_id": ...})` key distinct from raw
        `status_tool` calls — so "lazy"/"replay" return instantly once a
        job has finished at least one live run, while the intermediate
        polling itself is never treated as cacheable.
        """
        wait_key = {"job_id": job_id, "status_tool": status_tool, **extra_kwargs}
        if self._cache is not None and self._mode != "live":
            if self._cache.has("wait_for_job", wait_key):
                return self._cache.get("wait_for_job", wait_key)
            if self._mode == "replay":
                raise CacheMiss(
                    f"No cached terminal result for wait_for_job({job_id!r}) and mode "
                    "is 'replay'. Re-run with mode='lazy' or 'live' once to record it."
                )

        start = time.monotonic()
        while True:
            status = payload(await call(self._session, status_tool, {"job_id": job_id, **extra_kwargs}))
            state = _extract_state(status)
            if state in _TERMINAL_STATES:
                if self._cache is not None and self._mode != "replay":
                    self._cache.put("wait_for_job", wait_key, status)
                return status
            if time.monotonic() - start > timeout:
                raise TimeoutError(
                    f"wait_for_job({job_id!r}) did not reach a terminal state within "
                    f"{timeout}s (last seen: {state!r})"
                )
            await asyncio.sleep(poll_interval)


@asynccontextmanager
async def connect(
    params: StdioServerParameters,
    *,
    mode: Mode = "lazy",
    cache_dir: str | Path | None = None,
):
    """Open an MCP stdio session against `params` and yield an `HpcClient`.

    `params` is typically `dev_params(...)` or `pinned_params(...)`.
    `cache_dir` is required for "lazy"/"replay" — a cache-less client only
    makes sense with mode="live", where this is just thin sugar over
    `ClientSession`. Omit `cache_dir` (and leave mode="live") to skip
    caching entirely.

    Example:
        async with connect(dev_params("rikyu_mcp", "hpc_server"),
                            mode="lazy", cache_dir="./.hpc_cache/demo") as hpc:
            job = await hpc.submit_job(spec)
            status = await hpc.wait_for_job(job["job_id"])
    """
    if cache_dir is None and mode != "live":
        raise ValueError(f"mode={mode!r} needs cache_dir (nothing to read from/write to otherwise)")
    cache = Cache(cache_dir) if cache_dir is not None else None
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield HpcClient(session, mode=mode, cache=cache)


class SyncHpcClient:
    """Synchronous facade over `HpcClient` — no `await`, no `async with`.

    Not constructed directly — use `connect_sync()`. Runs `connect()`'s
    entire `async with` block — entry, every tool call, exit — as one
    single, long-lived coroutine on a background thread's event loop, and
    each sync method call hands that coroutine a request over a queue and
    blocks for the reply. So a notebook cell reads as plain
    `job = hpc.submit_job(spec=spec)`. Exceptions (`CacheMiss`, a tool
    error, `wait_for_job`'s `TimeoutError`, ...) propagate to the caller
    exactly as the async version raises them.

    Deliberately *not* "spin up a fresh asyncio Task per call via
    `run_coroutine_threadsafe`" — that was the first cut, and it's broken:
    the underlying MCP stdio transport uses anyio task groups, whose cancel
    scopes are tied to the specific asyncio Task they were entered in.
    Entering the session in one Task and exiting it in another raises
    `RuntimeError: Attempted to exit cancel scope in a different task than
    it was entered in`. Routing every call through one persistent task
    sidesteps that entirely.

    Only meant for the sequential, one-cell-at-a-time way a notebook
    actually runs — calling it concurrently from multiple Python threads
    isn't supported.
    """

    def __init__(self, params: StdioServerParameters, *, mode: Mode = "lazy",
                 cache_dir: str | Path | None = None) -> None:
        self._loop = asyncio.new_event_loop()
        self._requests: asyncio.Queue | None = None
        self._ready = threading.Event()
        self._init_error: BaseException | None = None
        self._thread = threading.Thread(
            target=self._run_loop, args=(params, mode, cache_dir), daemon=True,
        )
        self._thread.start()
        self._ready.wait()
        if self._init_error is not None:
            raise self._init_error

    def _run_loop(self, params, mode, cache_dir) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main(params, mode, cache_dir))
        finally:
            self._loop.close()

    async def _main(self, params, mode, cache_dir) -> None:
        self._requests = asyncio.Queue()
        try:
            async with connect(params, mode=mode, cache_dir=cache_dir) as hpc:
                self._ready.set()
                while True:
                    item = await self._requests.get()
                    if item is None:  # close() sentinel
                        return
                    name, args, kwargs, future = item
                    try:
                        result = await getattr(hpc, name)(*args, **kwargs)
                        future.set_result(result)
                    except BaseException as exc:  # noqa: BLE001 — must reach the caller's thread
                        future.set_exception(exc)
        except BaseException as exc:
            # Failed before (or while) opening the connection: __init__ is
            # still blocked on self._ready, hand it the error instead of
            # letting this thread die silently.
            if not self._ready.is_set():
                self._init_error = exc
                self._ready.set()
            else:
                raise

    def _call_sync(self, name: str, args: tuple, kwargs: dict) -> Any:
        future: concurrent.futures.Future = concurrent.futures.Future()
        self._loop.call_soon_threadsafe(self._requests.put_nowait, (name, args, kwargs, future))
        return future.result()

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)

        def sync_method(*args: Any, **kwargs: Any) -> Any:
            return self._call_sync(name, args, kwargs)

        return sync_method

    def close(self) -> None:
        """Close the underlying MCP session and stop the background loop.
        Call this in a notebook's last cell (or use `with connect_sync(...) as hpc:`)."""
        if self._requests is not None:
            self._loop.call_soon_threadsafe(self._requests.put_nowait, None)
        self._thread.join(timeout=10)

    def __enter__(self) -> "SyncHpcClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def connect_sync(
    params: StdioServerParameters,
    *,
    mode: Mode = "lazy",
    cache_dir: str | Path | None = None,
) -> SyncHpcClient:
    """Synchronous `connect()` — see `SyncHpcClient`. This is the one to
    reach for in a notebook or plain script.

    Example:
        hpc = connect_sync(dev_params("rikyu_mcp", "hpc_server"),
                            mode="lazy", cache_dir="./.hpc_cache/demo")
        job = hpc.submit_job(spec=spec)
        status = hpc.wait_for_job(job["job_id"])
        hpc.close()
    """
    return SyncHpcClient(params, mode=mode, cache_dir=cache_dir)
