#!/usr/bin/env python3
"""Update Env.csh from a Windows project path and ensure WSL venv exists."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path


KEY_VALUE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def win_to_wsl_path(win_path: str) -> str:
    normalized = os.path.abspath(win_path)
    drive, rest = os.path.splitdrive(normalized)

    if not drive or len(drive) < 2 or drive[1] != ":":
        raise ValueError(f"Expected a drive-letter Windows path, got: {win_path}")

    drive_letter = drive[0].lower()
    rest = rest.replace("\\", "/")
    return f"/mnt/{drive_letter}{rest}"


def parse_env(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = KEY_VALUE_RE.match(line)
        if not match:
            continue
        key, value = match.group(1), match.group(2)
        values[key] = value.strip()
    return values


def update_env_lines(lines: list[str], updates: dict[str, str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    for line in lines:
        match = KEY_VALUE_RE.match(line)
        if not match:
            out.append(line)
            continue

        key = match.group(1)
        if key in updates:
            out.append(f"{key} = {updates[key]}\n")
            seen.add(key)
        else:
            out.append(line)

    for key, value in updates.items():
        if key not in seen:
            if out and out[-1].strip():
                out.append("\n")
            out.append(f"{key} = {value}\n")

    return out


def ensure_wsl_venv(distro: str, wsl_project_path: str, venv_path: str, py_version: str | None) -> None:
    project_q = shlex.quote(wsl_project_path)
    venv_q = shlex.quote(venv_path)

    if py_version:
        create_cmd = (
            f"python{shlex.quote(py_version)} -m venv {venv_q} "
            f"|| python3 -m venv {venv_q}"
        )
    else:
        create_cmd = f"python3 -m venv {venv_q}"

    bash_cmd = (
        f"cd {project_q} && "
        f"if [ -d {venv_q} ]; then "
        f"echo 'WSL venv already present: {venv_path}'; "
        f"else {create_cmd}; fi"
    )

    cmd = ["wsl", "-d", distro, "--", "bash", "-lc", bash_cmd]
    subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Update Env.csh and ensure WSL venv exists.")
    parser.add_argument("--env-file", default="Env.csh", help="Path to Env.csh")
    parser.add_argument("--win-path", help="Windows project path (defaults to current directory)")
    args = parser.parse_args()

    env_path = Path(args.env_file).resolve()
    if not env_path.exists():
        print(f"[ERROR] Env file not found: {env_path}", file=sys.stderr)
        return 1

    win_path = args.win_path or os.getcwd()
    win_path = os.path.abspath(win_path)

    try:
        wsl_path = win_to_wsl_path(win_path)
    except ValueError as err:
        print(f"[ERROR] {err}", file=sys.stderr)
        return 1

    lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
    env_values = parse_env(lines)

    updates = {
        "WIN_PROJECT_PATH": win_path,
        "WSL_PROJECT_PATH": wsl_path,
    }

    new_lines = update_env_lines(lines, updates)
    env_path.write_text("".join(new_lines), encoding="utf-8")

    distro = env_values.get("WSL_DISTRO", "Ubuntu")
    venv_path = env_values.get("WSL_VENV_PATH", ".wsl_venv")
    py_version = env_values.get("WSL_PYTHON_VERSION")

    print("Updated Env.csh:")
    print(f"  WIN_PROJECT_PATH = {win_path}")
    print(f"  WSL_PROJECT_PATH = {wsl_path}")
    print(f"  WSL_DISTRO       = {distro}")
    print(f"  WSL_VENV_PATH    = {venv_path}")

    try:
        ensure_wsl_venv(distro, wsl_path, venv_path, py_version)
    except subprocess.CalledProcessError as err:
        print(f"[ERROR] Failed to ensure WSL venv: {err}", file=sys.stderr)
        return err.returncode or 1

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
