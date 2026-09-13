#!/usr/bin/env python3
"""Block only when all four progress conditions are known to hold."""

import json
import os
from pathlib import Path
import sys


EXCLUDED = {".scratch", ".git", ".claude", ".codex", "node_modules", ".venv",
            "venv", "__pycache__", "dist", "build", ".next", "target"}


def walk_error(error):
    raise error


def task_scope(root, lines):
    if not lines or not lines[0].startswith("Scope:"):
        return None
    value = lines[0][len("Scope:"):].strip()
    trimmed = value.rstrip("/")
    parts = trimmed.split("/")
    if (not trimmed or value.startswith("/") or "\\" in value
            or any(part in ("", ".", "..") for part in parts)):
        raise ValueError("invalid Scope")
    path = root.joinpath(*parts).resolve()
    path.relative_to(root)
    if path.exists() and not path.is_dir():
        raise ValueError("Scope is not a directory")
    return path


def main():
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        return
    if payload.get("stop_hook_active", False) is not False:
        return
    cwd = payload.get("cwd", os.getcwd())
    if not isinstance(cwd, str) or not cwd:
        return
    cwd = Path(cwd).resolve()
    if not cwd.is_dir():
        return
    root = next((p for p in (cwd, *cwd.parents)
                 if (p / ".scratch").is_dir()), None)
    if root is None:
        return
    scratch = root / ".scratch"
    marker = scratch / ".session"
    if scratch.is_symlink() or marker.is_symlink() or not marker.is_file():
        return
    session_mtime = marker.stat().st_mtime_ns
    tasks = []
    for task in sorted(scratch.iterdir()):
        if task.name == "archive" or not task.is_dir():
            continue
        spec = task / "spec.md"
        try:
            spec.lstat()
        except FileNotFoundError:
            continue
        if not spec.is_file():
            return
        with spec.open(encoding="utf-8") as stream:
            if stream.readline().strip() == "Status: in-progress":
                tasks.append((spec, task_scope(root, stream.read().splitlines())))
    if not tasks:
        return
    if len(tasks) == 1:
        spec, scope = tasks[0]
    else:
        matches = []
        for task in tasks:
            if task[1] is not None:
                try:
                    cwd.relative_to(task[1])
                except ValueError:
                    continue
                matches.append(task)
        if len(matches) != 1:
            return
        spec, scope = matches[0]
    name = spec.parent.name
    if "\n" in name or "\r" in name:
        return
    spec_mtime = spec.stat().st_mtime_ns
    if (scope is not None
            and any(part in EXCLUDED for part in scope.relative_to(root).parts)):
        return
    newest = session_mtime
    count = 0
    for directory, dirs, files in os.walk(
            root if scope is None else scope, onerror=walk_error, followlinks=False):
        dirs[:] = [name for name in dirs if name not in EXCLUDED]
        for filename in files:
            count += 1
            if count > 20000:
                return
            path = Path(directory) / filename
            if path.is_symlink():
                continue
            newest = max(newest, path.stat().st_mtime_ns)
    if newest > session_mtime and newest > spec_mtime:
        return {"decision": "block", "reason": (
            f"[harness] Task {name} 本轮有代码改动但进展未更新:"
            f"在 .scratch/{name}/spec.md 的 ## 进展 末尾追加一行"
            "(done / next / 别再试)再停。")}


if __name__ == "__main__":
    try:
        output = main()
        if output is not None:
            os.write(1, (json.dumps(output, ensure_ascii=False) + "\n").encode("utf-8"))
    except Exception:
        pass
