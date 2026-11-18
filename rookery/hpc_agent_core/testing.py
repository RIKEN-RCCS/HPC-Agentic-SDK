"""Shared MCP stdio smoke-test plumbing — see PORTING.md §9 for the tiered
pattern this backs (offline / read-only / job).

Only the genuinely machine-agnostic pieces live here: a collision-safe job
name and a pass/fail/skip summary. `call`/`payload` (reading a tool result
correctly) now live in `hpc_agent_core.client` — that module is the public,
notebook/script-facing client, and this file's own tests are just one of
its consumers; re-exported here so every machine repo's existing
`from hpc_agent_core.testing import ... call ... payload` import keeps
working unchanged. The tier functions themselves (which tools to check,
what a live call should assert, the job spec shape) stay in each machine
repo's own tests/smoke.py — they differ too much machine to machine to be
worth forcing into a shared shape, and a machine repo has no write access
here to adjust one anyway if it didn't. If you're tempted to centralize the
orchestration too, read PORTING.md §9's note on why it deliberately isn't.
"""
from __future__ import annotations

import os
import secrets
from collections.abc import Awaitable

from .client import call, payload

__all__ = [
    "call", "payload", "job_name", "Summary", "run_tier", "confirm_billing_gate",
]


def job_name(prefix: str) -> str:
    """A run-scoped job name so two concurrent smoke runs never collide."""
    return f"{prefix}-{os.getpid()}-{secrets.token_hex(4)}"


class Summary:
    """Tracks passed/failed/skipped tiers; one final summary line, with
    skips named rather than folded silently into the passed count."""

    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[tuple[str, BaseException]] = []
        self.skipped: list[tuple[str, str]] = []

    def ok(self, tier: str) -> None:
        self.passed.append(tier)

    def fail(self, tier: str, exc: BaseException) -> None:
        self.failed.append((tier, exc))

    def skip(self, tier: str, reason: str) -> None:
        self.skipped.append((tier, reason))

    @property
    def all_passed(self) -> bool:
        return not self.failed

    def line(self) -> str:
        skipped_str = "; ".join(f"{tier} ({reason})" for tier, reason in self.skipped)
        out = f"SUMMARY passed={len(self.passed)} failed={len(self.failed)} skipped={len(self.skipped)}"
        if self.skipped:
            out += f" SKIPPED({skipped_str})"
        return out


async def run_tier(summary: Summary, name: str, coro: Awaitable, *, stderr_print=print) -> None:
    """Run one tier, recording the outcome on summary and printing a
    PASSED/FAILED line. Never raises — check summary.all_passed after."""
    try:
        await coro
        summary.ok(name)
        print(f"[{name}] tier: PASSED")
    except Exception as exc:
        summary.fail(name, exc)
        stderr_print(f"[{name}] tier: FAILED — {exc}")


def confirm_billing_gate(args, *, flag_name: str = "confirm_billing", job_flag: str = "job",
                          reason: str) -> str | None:
    """For a machine where a --job submission is billable: returns a refusal
    message if --job was given without the matching --confirm-billing flag,
    or None if it's safe to proceed (either --job wasn't requested, or both
    flags are present). Callers should print the message to stderr and exit
    non-zero before constructing any client — this must be checked before
    any SSH/async work starts.

    Optional — a machine with no billing concern (or no usage cap concern)
    just doesn't call this.
    """
    if getattr(args, job_flag, False) and not getattr(args, flag_name, False):
        return (
            f"Refusing to submit: --{job_flag.replace('_', '-')} was given without "
            f"--{flag_name.replace('_', '-')}.\n{reason}\n"
            "No client was constructed and no SSH connection was attempted."
        )
    return None
