#!/usr/bin/env python3
"""Inject the active Task summary; failures leave the session unblocked."""

import json
import os
from pathlib import Path
import sys


def task_scope(root, lines):
    if not lines or not lines[0].startswith("Scope:"):
        return None, None, lines
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
    return "/".join(parts) + "/", path, lines[1:]


def task_context(name, lines):
    progress = "无"
    in_progress = False
    for line in lines:
        line = line.strip()
        if line == "## 进展":
            in_progress = True
        elif in_progress:
            if line.startswith(("# ", "## ")):
                break
            if line:
                progress = line
    return (f"[harness] Task: {name}(.scratch/{name}/spec.md)\n"
            f"状态: in-progress\n进展: {progress}")


def main():
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
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
    if scratch.is_symlink():
        return
    tasks = []
    for task in sorted(scratch.iterdir()):
        if task.name == "archive" or not task.is_dir():
            continue
        spec_path = task / "spec.md"
        try:
            spec_path.lstat()
        except FileNotFoundError:
            continue
        if not spec_path.is_file():
            return
        with spec_path.open(encoding="utf-8") as spec:
            if spec.readline().strip() == "Status: in-progress":
                scope_name, scope_path, lines = task_scope(
                    root, spec.read().splitlines())
                tasks.append((task.name, scope_name, scope_path, lines))
    if not tasks or any("\n" in task[0] or "\r" in task[0] for task in tasks):
        return
    if len(tasks) > 1:
        matches = []
        for task in tasks:
            if task[2] is not None:
                try:
                    cwd.relative_to(task[2])
                except ValueError:
                    continue
                matches.append(task)
        if len(matches) == 1:
            name, _, _, lines = matches[0]
            context = task_context(name, lines)
        else:
            summary = ", ".join(
                f"{name}(Scope: {scope or 'all-project'})"
                for name, scope, _, _ in tasks)
            context = (f"[harness] 有 {len(tasks)} 个 in-progress Task: {summary};"
                       "进对应 Scope 的目录开会话可注入该 Task 的详情")
    else:
        name, _, _, lines = tasks[0]
        context = task_context(name, lines)
    return {"hookSpecificOutput": {
        "hookEventName": "SessionStart", "additionalContext": context}}


if __name__ == "__main__":
    try:
        output = main()
        if output is not None:
            os.write(1, (json.dumps(output, ensure_ascii=False) + "\n").encode("utf-8"))
    except Exception:
        pass
