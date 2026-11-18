"""Facility registry shared by every facility served by the unified server.

Unlike the old per-repo `hpc-agent-core`, one process here serves *every*
onboarded machine at once, so settings can't live in one process-wide
global — they're keyed by an explicit facility slug (e.g. "rikyu",
"rccs-cloud") that the agent passes on every tool call.

A facility's own `facilities/<slug>/facility.py` calls `register_facility()`
once, at import time (triggered by `server/hpc_mcp`'s top-level import of
every `facilities/*/facility.py`), before anything in that facility's own
module touches config:

    # facilities/rikyu/facility.py
    from pathlib import Path
    from hpc_agent_core import config as _core

    FACILITY = _core.register_facility(
        slug="rikyu",
        display_name="RIKYU (AI4S / GB200)",
        description="RIKEN AI4S GB200 GPU cluster, Slurm, gpus_total dialect.",
        default_host="login.rikyu.r-ccs.riken.jp",
        data_dir=Path(__file__).parent / "data",
        embed_base_url="http://llm.ai.r-ccs.riken.jp:11434/v1",
        embed_model="bge-m3:567m",
    )

Every other hpc_agent_core module (middleware, rag.embed, doctor) takes a
facility (a `Facility` instance or its slug — `resolve()` accepts either)
rather than reading a process-wide global, which is what lets one
`middleware.run_command(facility, cmd)` etc. work unmodified across every
onboarded machine in the same process.

Settings resolve in order: environment variable > that facility's config
file > the registered default. The config file lives at
`~/.hpc-agent/<slug>.json` — one common directory, one file per facility.
`<SLUG_UPPER>_CONFIG` overrides it to an arbitrary path. No credentials are
stored in this module — SSH is key-based, and the only secret ever handled
here is an optional embedding API key, read per-call rather than cached, so
a changed key takes effect without a restart.
"""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path


#: The full remotemanager Computer/URL/Script constructor surface a facility
#: may want to override. "host" is deliberately excluded — it's already
#: governed by ssh_host()'s own env > file > default chain, so it isn't
#: duplicated here. Kept as a constant so middleware.py and any facility
#: inspecting valid keys have one source of truth instead of a string
#: literal repeated in two places.
COMPUTER_OPTION_NAMES = frozenset({
    # URL.__init__
    "user", "port", "verbose", "timeout", "max_timeouts", "python",
    "submitter", "shell", "raise_errors", "error_ignore_patterns", "keyfile",
    "passfile", "envpass", "sshpass_override", "cmd_history_depth",
    "landing_dir", "ssh_insert", "ssh_prepend", "ssh_override", "quiet_ssh",
    "shebang", "transport",
    # Script.__init__
    "template", "template_path", "empty_treatment", "header_only",
})

#: Sensible defaults matching what every facility needs identically unless
#: it genuinely differs: a login shell template, bash submitter, python3.
_BASE_COMPUTER_DEFAULTS = {
    "template": "#!/bin/bash -l",
    "submitter": "bash",
    "python": "python3",
}


@dataclass(frozen=True)
class Facility:
    """One onboarded machine's registered settings.

    `slug` is the identifier the agent passes on every facility-scoped tool
    call (submit_job(facility="rikyu", ...), search_docs(facility=...), ...).
    `display_name`/`description` are what `get_facilities()` shows an agent
    deciding which slug to use, and what scripts/render_facility_tables.py
    renders into skill files and README.md.
    """
    slug: str
    display_name: str
    description: str
    default_host: str
    data_dir: Path
    embed_base_url: str = ""
    embed_model: str = ""
    docs_filename: str = ""
    facts_filename: str = ""
    docs_cite_url: str = ""
    computer_defaults: dict = field(default_factory=dict)
    #: The exact JSON an unconfigured user should write, as a dict. Rendered
    #: into the setup directions every tool returns when this facility isn't
    #: reachable yet — so it must be genuinely copy-pasteable, including any
    #: extra keys this machine requires beyond ssh.host.
    config_example: dict = field(default_factory=dict)
    #: Machine-specific setup prose for those same directions: where a key
    #: gets registered, the real login hostname, anything that must be true
    #: before the first connection can work. A few short lines, imperative.
    setup_help: str = ""

    @property
    def env_prefix(self) -> str:
        return self.slug.upper().replace("-", "_")


_REGISTRY: dict[str, Facility] = {}


def register_facility(*, slug: str, display_name: str, description: str,
                       default_host: str, data_dir: Path,
                       embed_base_url: str = "", embed_model: str = "",
                       docs_filename: str | None = None,
                       facts_filename: str | None = None,
                       docs_cite_url: str = "",
                       computer_defaults: dict | None = None,
                       config_example: dict | None = None,
                       setup_help: str = "") -> Facility:
    """Register a facility. Call exactly once per slug, at import time,
    before any other hpc_agent_core module is used for that facility.

    docs_filename (the bundled guide, under data_dir) defaults to
    "<slug>_guide.md". facts_filename (the static facts JSON get_facility()
    returns, under data_dir) defaults to "<slug>_config.json" — override it
    to reuse an existing data file with a different name verbatim rather
    than renaming it. docs_cite_url (see PORTING.md) is the URL search
    results should cite — leave blank (the default) when there's no live
    docs site worth pointing users at.
    computer_defaults overrides any of COMPUTER_OPTION_NAMES for this
    facility's remotemanager.Computer (see computer_kwargs()) — e.g. a
    facility whose login shell needs a different `shell`, a longer
    `timeout`, or a specific `keyfile`.
    """
    if slug in _REGISTRY:
        raise ValueError(f"Facility {slug!r} is already registered")
    unknown = set((computer_defaults or {})) - COMPUTER_OPTION_NAMES
    if unknown:
        raise ValueError(f"computer_defaults has unknown Computer option(s): {sorted(unknown)}")
    fac = Facility(
        slug=slug,
        display_name=display_name,
        description=description,
        default_host=default_host,
        data_dir=Path(data_dir),
        embed_base_url=embed_base_url,
        embed_model=embed_model,
        docs_filename=docs_filename or f"{slug.replace('-', '_')}_guide.md",
        facts_filename=facts_filename or f"{slug.replace('-', '_')}_config.json",
        docs_cite_url=docs_cite_url,
        computer_defaults=dict(computer_defaults or {}),
        config_example=dict(config_example or {"ssh": {"host": default_host}}),
        setup_help=setup_help.strip(),
    )
    _REGISTRY[slug] = fac
    return fac


def list_facilities() -> list[Facility]:
    """Every registered facility, in registration order."""
    return list(_REGISTRY.values())


def get_facility(slug: str) -> Facility:
    """The registered Facility for `slug`. Raises ValueError listing every
    valid slug if `slug` isn't registered — this is the mechanism that
    makes a wrong/guessed facility name fail loudly and correctably rather
    than silently reading someone else's settings."""
    try:
        return _REGISTRY[slug]
    except KeyError:
        valid = ", ".join(sorted(_REGISTRY)) or "(none registered)"
        raise ValueError(
            f"Unknown facility {slug!r}. Valid facilities: {valid}. "
            "Call get_facilities() to see the full list with descriptions."
        ) from None


def resolve(facility: "Facility | str") -> Facility:
    """Accept either a Facility instance or a slug; always return a Facility."""
    return facility if isinstance(facility, Facility) else get_facility(facility)


def config_path(facility: "Facility | str") -> Path:
    """Path to the facility's user config file (may not exist).
    <SLUG_UPPER>_CONFIG overrides it to an arbitrary path; otherwise it's
    ~/.hpc-agent/<env_prefix.lower()>.json — the same filename the original
    per-repo hpc-agent-core used (env_prefix.lower(), not the slug itself,
    so an already-configured facility like "rccs-cloud" whose file is
    ~/.hpc-agent/rccs_cloud.json (underscore) keeps working unmodified)."""
    fac = resolve(facility)
    env_override = os.environ.get(f"{fac.env_prefix}_CONFIG")
    if env_override:
        return Path(env_override).expanduser()
    return Path(f"~/.hpc-agent/{fac.env_prefix.lower()}.json").expanduser()


def setup_instructions(facility: "Facility | str", *, problem: str = "",
                        ssh_error: str = "") -> str:
    """The setup directions any tool returns when a facility can't be reached.

    Composed here, in one place, so every facility's directions have the
    same shape — what's wrong, the exact file to write, the machine's own
    prerequisites, how to verify, and which skill walks through it
    interactively. The machine-specific parts come from that facility's
    registered `config_example` and `setup_help`; nothing here is
    hardcoded per machine.

    This is what an agent shows a user who says "I want to use this
    machine" before anything is set up, so it has to be actionable on its
    own — not a pointer to documentation the agent may not be able to open.
    """
    fac = resolve(facility)
    example = json.dumps(fac.config_example, indent=2)
    lines = [
        problem or f"Facility {fac.slug!r} ({fac.display_name}) is not configured yet, "
                    f"so this call cannot reach the cluster.",
        "",
        f"1. Create {config_path(fac)} containing:",
        "",
        *(f"     {line}" for line in example.splitlines()),
        "",
    ]
    if fac.setup_help:
        lines += ["2. " + fac.setup_help.splitlines()[0],
                  *(f"   {line}" for line in fac.setup_help.splitlines()[1:]),
                  ""]
        step = 3
    else:
        step = 2
    lines += [
        f"{step}. Verify with:  hpc-doctor {fac.slug}",
        "",
        f"The {fac.slug}-configuring skill walks through this interactively, "
        f"and can write the file for you.",
    ]
    if ssh_error:
        lines += ["", f"Underlying connection error: {ssh_error}"]
    return "\n".join(lines)


def file_config(facility: "Facility | str") -> dict:
    """The parsed user config file for `facility`, or {} if absent. Raises
    on malformed JSON.

    Public because a facility legitimately needs to read its own
    *user-level* settings — ones that are a per-user choice rather than a
    bundled cluster fact, so they belong in ~/.hpc-agent/<slug>.json rather
    than in data/<slug>_config.json. HBW2's mandatory project/account
    (`defaults.account`) is the motivating case: core has no business
    knowing what an "account" is, but a facility's own apply_defaults()
    can read one from here. Read at call time, never cached, so a config
    edit takes effect on the next tool call.
    """
    path = config_path(facility)
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Malformed config file {path}: {e}") from e


def require_facility_configuration(facility: "Facility | str") -> Facility:
    """Return ``facility`` only when the user explicitly configured SSH.

    A registered default host is descriptive metadata, not user setup.  MCP
    entry points call this before dispatching any facility-scoped operation so
    an unconfigured facility cannot appear available merely because a default
    hostname happens to resolve.  ``<PREFIX>_HOST`` is the supported
    file-free configuration override; otherwise the selected config file must
    exist, parse as JSON, and contain a non-empty ``ssh.host``.
    """
    fac = resolve(facility)
    path = config_path(fac)
    if os.environ.get(f"{fac.env_prefix}_HOST", "").strip():
        return fac
    if not path.exists():
        raise RuntimeError(setup_instructions(fac))
    try:
        contents = file_config(fac)
    except Exception as exc:
        raise RuntimeError(setup_instructions(
            fac, problem=f"Configuration file {path} could not be read: {exc}",
        )) from exc
    host = contents.get("ssh", {}).get("host") if isinstance(contents, dict) \
        and isinstance(contents.get("ssh"), dict) else ""
    if not isinstance(host, str) or not host.strip():
        raise RuntimeError(setup_instructions(
            fac,
            problem=(f"Configuration file {path} must set a non-empty "
                     '"ssh.host" destination before this facility can be used.'),
        ))
    return fac


def _section(facility: "Facility | str", key: str) -> dict:
    """A dict-typed top-level section of the config file, or {} if the key
    is absent *or* explicitly null (`{"ssh": null}` is valid JSON and an
    easy hand-edit mistake — `.get(key, {})` alone only supplies the
    default when the key is missing, not when its value is None, so callers
    must not use that pattern directly for these sections)."""
    return file_config(facility).get(key) or {}


def ssh_host(facility: "Facility | str") -> str:
    """SSH destination for the facility's login node: a ~/.ssh/config
    alias, a plain user@hostname, or "localhost" (or a 127.* address) for
    running directly on the cluster's own front-end/login node with no SSH
    at all — remotemanager's URL.is_local routes that case to a bare local
    shell (see hpc_agent_core.middleware.get_frontend()'s docstring)."""
    fac = resolve(facility)
    return (os.environ.get(f"{fac.env_prefix}_HOST")
            or _section(fac, "ssh").get("host")
            or fac.default_host)


def embed_api_key(facility: "Facility | str") -> str:
    """API key for the facility's embedding endpoint (the only
    user-configurable embedding setting — model/base_url are fixed per
    facility). Resolved in order: <SLUG_UPPER>_EMBED_API_KEY, then the
    shared RCCS_EMBED_API_KEY (a common fallback across RIKEN R-CCS
    facilities that point at the same endpoint), then embedding.api_key in
    the config file. Empty string means no auth header is sent."""
    fac = resolve(facility)
    return (os.environ.get(f"{fac.env_prefix}_EMBED_API_KEY")
            or os.environ.get("RCCS_EMBED_API_KEY")
            or _section(fac, "embedding").get("api_key") or "")


def docs_source(facility: "Facility | str") -> Path:
    """Path to the bundled guide markdown that rag/ingest.py chunks."""
    fac = resolve(facility)
    return fac.data_dir / fac.docs_filename


def load_facts(facility: "Facility | str") -> dict:
    """The facility's static facts (partitions, storage, modules, ...) —
    bundled data under data_dir, not the user's config file. This is what
    the get_facility MCP tool returns."""
    fac = resolve(facility)
    with open(fac.data_dir / fac.facts_filename) as f:
        return json.load(f)


def docs_index_dir(facility: "Facility | str") -> Path:
    """Directory for the built docs index (chunks.json + optional
    embeddings.npy)."""
    fac = resolve(facility)
    return Path(os.environ.get(f"{fac.env_prefix}_DOCS_INDEX", fac.data_dir / "docs_index"))


def docs_cite_url(facility: "Facility | str") -> str:
    """URL search results should cite, or "" to cite nothing."""
    return resolve(facility).docs_cite_url


def computer_kwargs(facility: "Facility | str") -> dict:
    """Resolved kwargs for constructing this facility's remotemanager.Computer
    (everything except `host`, which stays governed by ssh_host()).

    Precedence: _BASE_COMPUTER_DEFAULTS < the facility's own
    register_facility(computer_defaults=...) < a "computer" object in the
    end user's config file."""
    fac = resolve(facility)
    resolved = dict(_BASE_COMPUTER_DEFAULTS)
    resolved.update(fac.computer_defaults)
    file_overrides = _section(fac, "computer")
    unknown = set(file_overrides) - COMPUTER_OPTION_NAMES
    if unknown:
        raise RuntimeError(
            f"{config_path(fac)}: \"computer\" has unknown option(s): {sorted(unknown)}"
        )
    resolved.update(file_overrides)
    return resolved
