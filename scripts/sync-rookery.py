"""Refresh the SDK's filtered Rookery distribution from an upstream Git checkout."""

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "https://github.com/william-dawson/hpc-rookery"
SDK_REMOTE = "https://github.com/RIKEN-RCCS/HPC-Agentic-SDK.git"
SOURCE = f"git+{SDK_REMOTE}@main#subdirectory=rookery"
FACILITIES = ("fugaku", "hokusai", "rccs-cloud", "rikyu")
RENDER_TABLES = "scripts/render_facility_tables.py"


def git(checkout, *args):
    return subprocess.check_output(["git", "-C", str(checkout), *args])


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def sync(checkout, ref):
    revision = git(checkout, "rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()
    paths = [
        ".gitignore", "LICENSE", "pyproject.toml", "hpc_agent_core", "hpc_mcp",
        "facilities/__init__.py", "facilities/registry.py", "plugins/hpc", RENDER_TABLES,
        *[f"facilities/{slug.replace('-', '_')}" for slug in FACILITIES],
        *[f"plugins/hpc-{slug}" for slug in FACILITIES],
    ]
    archive = git(checkout, "archive", "--format=tar", revision, "--", *paths)

    with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
        staged = Path(temporary) / "rookery"
        staged.mkdir()
        with tarfile.open(fileobj=BytesIO(archive)) as tar:
            tar.extractall(staged, filter="data")

        fugaku_compute = staged / "facilities/fugaku/compute.py"
        if fugaku_compute.exists():
            source = fugaku_compute.read_text(encoding="utf-8")
            fugaku_compute.write_text(source.replace("self.facility, \n", "self.facility,\n"), encoding="utf-8")

        (staged / "README.md").write_text(
            "# HPC Rookery in the HPC Agentic SDK\n\n"
            f"Filtered distribution of [HPC Rookery]({UPSTREAM}/tree/{revision}).\n"
            f"Included facilities are {', '.join(FACILITIES)}.\n"
            "See [LICENSE](./LICENSE) and [UPSTREAM.json](./UPSTREAM.json).\n",
            encoding="utf-8",
        )
        write_json(staged / "UPSTREAM.json", {
            "repository": UPSTREAM, "revision": revision, "facilities": FACILITIES,
        })

        with (staged / "plugins/hpc/.mcp.json").open(encoding="utf-8") as manifest:
            servers = json.load(manifest)["mcpServers"]
        for name, config in servers.items():
            args = config["args"]
            source_arg = args.index("--from") + 1
            args[source_arg] = SOURCE
        base = staged / "plugins/hpc"
        write_json(base / ".mcp.json", {"mcpServers": servers})
        portable = json.loads((base / "mcp.json").read_text(encoding="utf-8"))
        for name, config in portable["mcpServers"].items():
            config.update(servers[name])
        write_json(base / "mcp.json", portable)

        subprocess.run([sys.executable, staged / RENDER_TABLES], check=True)
        discovery = base / "skills/hpc-facilities/SKILL.md"
        instructions = discovery.read_text(encoding="utf-8").replace(
            "codex plugin add hpc-<slug>@hpc-marketplace",
            "codex plugin add hpc-<slug>@hpc-agentic-sdk",
        )
        instructions = instructions.replace(
            "For a harness without plugins, install only",
            "In OpenCode or Pi, use `/hpc-sdk` to list the current selection, then "
            "add `hpc-<slug>` to that selection with `/hpc-sdk set`.\n\n"
            "For a harness without plugins, install only",
        ).replace(
            "`plugins/hpc-<slug>/skills/`", "`rookery/plugins/hpc-<slug>/skills/`",
        )
        discovery.write_text(instructions, encoding="utf-8")
        for skill in (staged / "plugins").glob("hpc-*/skills/*/SKILL.md"):
            original = skill.read_text(encoding="utf-8")
            updated = original.replace(f"git+{UPSTREAM}.git@main", f"'{SOURCE}'")
            if skill.parent.name.endswith("-reproducing"):
                updated = updated.replace(f"{UPSTREAM}.git", SDK_REMOTE).replace(
                    '        ref="main",\n', '        ref="main",\n        subdirectory="rookery",\n',
                ).replace(
                    "There is no `subdirectory=` argument — this repo's Python project lives at\n"
                    "its own root.",
                    "Use `subdirectory=\"rookery\"` for the SDK bundle. Pin `ref` to an SDK tag or commit "
                    "when saving a notebook for later replay.",
                )
            if updated != original:
                skill.write_text(updated, encoding="utf-8")
        shutil.rmtree(staged / "scripts")
        destination = ROOT / "rookery"
        previous = Path(temporary) / "previous"
        if destination.exists():
            destination.rename(previous)
        try:
            staged.rename(destination)
        except OSError:
            if previous.exists():
                previous.rename(destination)
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("--ref", default="HEAD")
    args = parser.parse_args()
    sync(args.checkout, args.ref)
