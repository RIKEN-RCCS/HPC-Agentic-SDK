"""Facility slug -> SchedulerBackend registry.

Kept separate from hpc_agent_core.config.Facility (which holds connection/
docs/embedding settings, not a scheduler backend) so hpc_agent_core stays
scheduler-agnostic — it defines SchedulerBackend, but has no reason to know
which concrete backend instance belongs to which facility. Each
facilities/<slug>/facility.py calls register_backend(SLUG, BACKEND) right
after building its backend; server/hpc_mcp imports every facility module
(registering both the Facility and its backend) before serving.
"""
from hpc_agent_core.compute.base import SchedulerBackend

_BACKENDS: dict[str, SchedulerBackend] = {}


def register_backend(slug: str, backend: SchedulerBackend) -> None:
    if slug in _BACKENDS:
        raise ValueError(f"Backend for facility {slug!r} is already registered")
    _BACKENDS[slug] = backend


def get_backend(slug: str) -> SchedulerBackend:
    try:
        return _BACKENDS[slug]
    except KeyError:
        valid = ", ".join(sorted(_BACKENDS)) or "(none registered)"
        raise ValueError(
            f"Unknown facility {slug!r}. Valid facilities: {valid}. "
            "Call get_facilities() to see the full list with descriptions."
        ) from None
