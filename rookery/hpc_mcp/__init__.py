"""Importing this package registers every onboarded facility.

Every directory under facilities/ containing a facility.py is imported
(triggering its config.register_facility() + registry.register_backend()
calls) — a new facility PR that adds facilities/<slug>/facility.py needs no
edit here to be picked up; that's deliberate, so parallel facility PRs don't
conflict on this file. Every hpc_mcp entry point (hpc_server, docs_server,
doctor, ingest) imports hpc_mcp first (even just for this side effect)
before doing anything that needs a registered facility.

**A facility that fails to import must not take the server down with it.**
This is the "never fail to start" invariant (PORTING.md §10) applied at the
place the hub made it sharper: one process now serves every facility, so an
exception in one facility.py — a typo, a bad register_facility argument, a
missing data file — would otherwise deny every *other* facility to every
user. Such a facility is skipped, its error recorded in FAILED_FACILITIES,
and the server starts with the rest. It is never skipped silently:
get_facilities() reports it, and the doctor fails on it.
"""
import importlib
import pkgutil

import facilities

#: slug -> the error that stopped it loading. Populated at import time;
#: read by hpc_server.get_facilities() and hpc_agent_core.doctor so a
#: facility can never disappear without explanation.
FAILED_FACILITIES: dict[str, str] = {}

for _mod in pkgutil.iter_modules(facilities.__path__):
    if not _mod.ispkg:
        continue  # skip registry.py itself — only facility subpackages
    try:
        importlib.import_module(f"facilities.{_mod.name}.facility")
    except ModuleNotFoundError as exc:
        # A subdirectory with no facility.py at all (e.g. __pycache__) is
        # not a facility and not an error. But a facility.py that exists
        # and imports something missing is a real failure, so only the
        # former is skipped quietly.
        if exc.name in (f"facilities.{_mod.name}.facility", f"facilities.{_mod.name}"):
            continue
        FAILED_FACILITIES[_mod.name] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:  # noqa: BLE001 -- deliberate: see module docstring
        FAILED_FACILITIES[_mod.name] = f"{type(exc).__name__}: {exc}"
