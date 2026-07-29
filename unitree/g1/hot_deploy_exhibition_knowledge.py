#!/usr/bin/env python3
"""Temporarily install the exhibition knowledge card into a running G1 driver.

This is only for on-robot verification before the driver image is built. It
patches the running container's writable layer, so redeploying the driver image
will discard the test installation.
"""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONTAINER = "embodied-unitree-g1"
MAIN_MARKER = '        if plugins_cfg.get("motion_switcher", {}).get("enabled", False):\n'
MAIN_INSERT = '''        if plugins_cfg.get("exhibition_knowledge", {}).get("enabled", False):
            from exhibition_knowledge import ExhibitionKnowledgePlugin
            self._plugins.append(ExhibitionKnowledgePlugin(plugins_cfg["exhibition_knowledge"], namespace, executor))
            print("[bundle] ExhibitionKnowledgePlugin loaded")

'''
CONFIG_MARKER = "  motion_switcher:\n"
CONFIG_INSERT = '''  exhibition_knowledge:
    enabled: true
    # Hot-deploy data is intentionally container-local and is not production persistence.
    data_path: /work/resource/knowledge/runtime-beijing-exhibition.json
    seed_path: /work/resource/knowledge/beijing-exhibition.json
'''


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def read_container_file(container: str, source: str, destination: Path) -> None:
    run("docker", "cp", f"{container}:{source}", str(destination))


def write_container_file(container: str, source: Path, destination: str) -> None:
    run("docker", "cp", str(source), f"{container}:{destination}")


def patched_text(content: str, marker: str, insert: str, installed_hint: str) -> str:
    if installed_hint in content:
        return content
    if marker not in content:
        raise RuntimeError(f"unable to find expected patch marker: {marker.strip()}")
    return content.replace(marker, insert + marker, 1)


def deploy(container: str) -> Path:
    if not (ROOT / "exhibition_knowledge.py").is_file():
        raise RuntimeError("run this script from the G1 driver source tree")
    if not (ROOT / "resource/knowledge/beijing-exhibition.json").is_file():
        raise RuntimeError("knowledge seed file is missing")

    backup = Path("/tmp") / f"g1-exhibition-knowledge-backup-{dt.datetime.now():%Y%m%d-%H%M%S}"
    backup.mkdir()
    read_container_file(container, "/work/main.py", backup / "main.py")
    read_container_file(container, "/work/config.yaml", backup / "config.yaml")

    main = patched_text((backup / "main.py").read_text(), MAIN_MARKER, MAIN_INSERT, "ExhibitionKnowledgePlugin")
    config = patched_text((backup / "config.yaml").read_text(), CONFIG_MARKER, CONFIG_INSERT, "  exhibition_knowledge:\n")
    with tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory)
        (temporary / "main.py").write_text(main)
        (temporary / "config.yaml").write_text(config)
        write_container_file(container, temporary / "main.py", "/work/main.py")
        write_container_file(container, temporary / "config.yaml", "/work/config.yaml")

    run("docker", "exec", container, "mkdir", "-p", "/work/resource/knowledge")
    write_container_file(container, ROOT / "exhibition_knowledge.py", "/work/exhibition_knowledge.py")
    write_container_file(container, ROOT / "resource/knowledge/beijing-exhibition.json", "/work/resource/knowledge/beijing-exhibition.json")
    run("docker", "restart", container)
    return backup


def restore(container: str, backup: Path) -> None:
    for name in ("main.py", "config.yaml"):
        source = backup / name
        if not source.is_file():
            raise RuntimeError(f"backup file is missing: {source}")
        write_container_file(container, source, f"/work/{name}")
    run("docker", "exec", container, "rm", "-f", "/work/exhibition_knowledge.py")
    run("docker", "exec", container, "rm", "-f", "/work/resource/knowledge/beijing-exhibition.json")
    run("docker", "exec", container, "rm", "-f", "/work/resource/knowledge/runtime-beijing-exhibition.json")
    run("docker", "restart", container)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default=CONTAINER)
    parser.add_argument("--restore-from", type=Path, help="restore a backup printed by a previous deployment")
    args = parser.parse_args()
    try:
        if args.restore_from:
            restore(args.container, args.restore_from)
            print(f"Restored {args.container} from {args.restore_from}")
        else:
            backup = deploy(args.container)
            print(f"Hot deployment complete. Backup: {backup}")
            print("This is temporary: driver image redeployment will remove the card and its test data.")
        return 0
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
