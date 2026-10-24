#!/usr/bin/env python3
"""Remind a session of its Task handoff, then check unrecorded code changes."""

import json
import os
from pathlib import Path
import re
import shlex
import sys

sys.dont_write_bytecode = True


EXCLUDED = {
    ".scratch",
    ".git",
    ".claude",
    ".codex",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".next",
    "target",
}


def walk_error(error):
    raise error


def task_scope(root, lines):
    if not lines or not lines[0].startswith("Scope:"):
        return None
    value = lines[0][len("Scope:") :].strip()
    trimmed = value.rstrip("/")
    parts = trimmed.split("/")
    if (
        not trimmed
        or value.startswith("/")
        or "\\" in value
        or any(part in ("", ".", "..") for part in parts)
    ):
        raise ValueError("invalid Scope")
    path = root.joinpath(*parts).resolve()
    path.relative_to(root)
    if path.exists() and not path.is_dir():
        raise ValueError("Scope is not a directory")
    return path


def reminder(task, busy):
    """Return the first applicable instruction for one claimed Task."""
    name = task["name"]
    if task["status"] == "done":
        source = shlex.quote(f".scratch/{name}")
        destination = shlex.quote(f".scratch/archive/{name}")
        return (
            f"[harness] Task {name} 已是 done 但还在 .scratch/:"
            f"在主工作树执行 mkdir -p .scratch/archive && mv {source} {destination}。"
        )
    checks = task["checks"]
    if not checks:
        return (
            f"[harness] Task {name} 的「## 验收」还没有带执行者的勾选框:"
            "改写成 - [ ] [我] … / - [ ] [你] …;[我] 是你当场能演示并自验的,"
            "[你] 是只有 owner 能做或要 owner 看的。"
        )
    mine = [check for check in checks if check[1] == "我"]
    if mine and all(check[0] for check in mine):
        return (
            f"[harness] Task {name} 的 [我] 验收项已全部勾上:现在做收件三问,"
            "改 Status: done 并归档;没勾的 [你] 项留在 spec 里,看板会继续列给 owner。"
        )
    ball = task["ball"]
    next_text = task["next"]
    if ball == "我" and not busy:
        return (
            f"[harness] Task {name} 的 next 是你自己的事({next_text[:60]}):接着做,"
            "做完勾上对应的验收项;[我] 项全勾就直接收件三问、改 done、归档,不要把核验或关闭写成「你:」。"
            "做不了就先追加一行进展,把 next 改成「你: <owner 要做的具体动作>」或"
            "「等: <在等什么>(回看: <几点、由谁、怎么看>)」再停;owner 让停或本轮在问别的事时写「等: owner 下一步安排(回看: owner 下次开口)」。"
        )
    if (
        ball == "等"
        and not busy
        and "回看:" not in next_text
        and "回看：" not in next_text
    ):
        return (
            f"[harness] Task {name} 在等外部但没写怎么回看:挂后台命令或 Monitor 等结果,"
            "或在 next 里补「回看: <几点、由谁、怎么看>」再停。"
        )
    if not task["progress"] or ball not in ("我", "等", "你"):
        return (
            f"[harness] Task {name} 的进展末行没写球在谁手里:"
            "追加一行进展,next 以「我:」「等:」「你:」开头。"
        )
    return None


def output_message(message, codex):
    if codex:
        return {"decision": "block", "reason": message}
    return {
        "hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": message}
    }


def read_tasks(root, read_task):
    """Read non-archived Tasks, skipping only malformed specs."""
    tasks = []
    for folder in sorted((root / ".scratch").iterdir()):
        if folder.name == "archive" or not folder.is_dir() or folder.is_symlink():
            continue
        spec = folder / "spec.md"
        try:
            task = read_task(spec, root)
        except (OSError, UnicodeError, ValueError):
            continue
        if "\n" in task["name"] or "\r" in task["name"]:
            continue
        tasks.append(task)
    return tasks


def spec_kind(lines):
    """Return the 类型 header value, or "" for a spec that predates the template."""
    for line in lines[1:]:
        if not line.strip() or line.startswith("#"):
            break
        match = re.match(r"^类型[：:]\s*(.*)$", line)
        if match:
            return match.group(1).strip()
    return ""


def spec_reminder(task, root, skeleton):
    """Collect all template violations for one parseable Task."""
    lines = task["spec"].read_text(encoding="utf-8").splitlines()
    sections = [(i, line[3:].strip()) for i, line in enumerate(lines) if line.startswith("## ")]
    progress = []
    for index, (start, title) in enumerate(sections):
        if title.startswith("进展"):
            end = sections[index + 1][0] if index + 1 < len(sections) else len(lines)
            progress = [line for line in lines[start + 1:end] if line.strip()]
            break
    problems = []
    if skeleton is not None:
        names = []
        optional = set()
        record_skips = set()
        for line in skeleton:
            if line.startswith("## "):
                names.append(line[3:].strip())
            elif names and line.strip() == "<!-- 记录可省 -->":
                record_skips.add(names[-1])
            elif names and line.strip().startswith("<选填"):
                optional.add(names[-1])
        kind = spec_kind(lines)
        required = [name for name in names if name not in (optional if kind == "功能" else record_skips)]
        missing = [name for name in required
                   if not any(title.startswith(name) for _, title in sections)]
        first_section = sections[0][0] if sections else len(lines)
        if not any(re.match(r"^目标[：:]", line) for line in lines[:first_section]):
            missing.insert(0, "目标")
        if missing:
            problems.append("缺必填节: " + "、".join(missing))
        extra = [title for _, title in sections if not any(title.startswith(name) for name in names)]
        if extra:
            problems.append("骨架以外的节: " + "、".join(extra))
        placeholders = {line.strip() for line in skeleton if re.search(r"<[^<>]+>", line)}
        if any(line.strip() in placeholders for line in lines):
            problems.append("还留着骨架占位行")
    if progress and len(progress[-1]) > 200:
        problems.append("进展最后一行超过 200 字")
    if sum(bool(re.match(r"^- \d{2}-\d{2}", line)) for line in progress) > 30:
        problems.append("进展超过 30 行")
    scope = task["scope"]
    if scope is not None and scope.is_relative_to(root / ".scratch"):
        problems.append("Scope 落在 .scratch 内")
    if problems:
        return (f"[harness] Task {task['name']} 的 spec 不合模板:"
                + ";".join(problems)
                + "。照 .agents/skills/interview-me/templates/spec.md 改好再停。")


def written_specs(payload, tasks, claimed):
    """List unclaimed template specs this session may have edited, using cheap checks only."""
    transcript = payload.get("transcript_path")
    if not isinstance(transcript, str) or not transcript or not Path(transcript).is_file():
        return []
    born = getattr(Path(transcript).stat(), "st_birthtime", None)
    owned = {task["spec"] for task in claimed}
    result = []
    for task in tasks:
        spec = task["spec"]
        if spec in owned or task["session"]:
            continue
        if not spec_kind(spec.read_text(encoding="utf-8").splitlines()):
            continue
        # A spec untouched since this transcript began cannot carry this session's edits.
        if born is not None and spec.stat().st_mtime < born:
            continue
        result.append(task)
    return result


def session_edits(payload):
    """Scan this session's transcripts once for files its edit tools wrote."""
    from stop_evidence import edited_paths

    transcript = Path(payload["transcript_path"])
    sources = [transcript]
    subagents = transcript.with_suffix("") / "subagents"
    if subagents.is_dir():
        sources.extend(subagents.rglob("*.jsonl"))
    paths = set()
    for source in sources:
        paths |= edited_paths(source)
    return paths


def legacy_reminder(payload, root, cwd, tasks, foreign=()):
    """Keep the existing code-change evidence and Scope selection behavior."""
    from stop_evidence import transcript_evidence

    if not tasks or root is None:
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
    if spec in foreign:
        return
    name = spec.parent.name
    if "\n" in name or "\r" in name:
        return
    spec_mtime = spec.stat().st_mtime_ns
    if scope is not None and any(
        part in EXCLUDED for part in scope.relative_to(root).parts
    ):
        return
    candidates = {}
    count = 0
    for directory, dirs, files in os.walk(
        root if scope is None else scope, onerror=walk_error, followlinks=False
    ):
        dirs[:] = [
            entry
            for entry in dirs
            if entry not in EXCLUDED and not (Path(directory) / entry).is_symlink()
        ]
        for filename in files:
            count += 1
            if count > 20000:
                return
            path = Path(directory) / filename
            if path.is_symlink():
                continue
            mtime = path.stat().st_mtime_ns
            if mtime > spec_mtime:
                candidates[path.resolve()] = mtime
    if not candidates:
        return
    transcript = payload.get("transcript_path")
    if (
        not isinstance(transcript, str)
        or not transcript
        or not Path(transcript).is_file()
    ):
        return
    transcript = Path(transcript)
    sources = [transcript]
    subagents = transcript.with_suffix("") / "subagents"
    if subagents.is_dir():
        sources.extend(subagents.rglob("*.jsonl"))
    if any(transcript_evidence(source, spec_mtime, candidates) for source in sources):
        return (
            f"[harness] Task {name} 本轮有代码改动但进展未更新:"
            f"在 .scratch/{name}/spec.md 的 ## 进展 末尾追加一行"
            "(done / next / 别再试)再停。"
        )


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
    # Import inside main so a missing or broken sibling hook also fails open.
    from session_start import project_roots, read_task, session_matches, template_skeleton

    scan_root, task_root = project_roots(cwd)
    if task_root is None:
        return
    scratch = task_root / ".scratch"
    if scratch.is_symlink():
        return
    tasks = read_tasks(task_root, read_task)
    session_id = payload.get("session_id")
    claimed = (
        [
            task
            for task in tasks
            if task["status"] in ("in-progress", "done")
            and session_matches(task["session"], session_id)
        ]
        if isinstance(session_id, str)
        else []
    )
    busy = bool(payload.get("background_tasks") or payload.get("session_crons"))
    try:
        skeleton = template_skeleton(task_root)
    except (OSError, UnicodeError, ValueError):
        skeleton = None
    messages = []
    for task in claimed:
        message = reminder(task, busy) or spec_reminder(task, task_root, skeleton)
        if message:
            messages.append(message)
    failing = [(task, message) for task in written_specs(payload, tasks, claimed)
               if (message := spec_reminder(task, task_root, skeleton))]
    # Transcripts run to hundreds of MB: scan once, and only when some spec fails.
    if failing:
        edits = session_edits(payload)
        messages.extend(message for task, message in failing if task["spec"].resolve() in edits)
    if messages:
        return output_message("\n".join(messages), "turn_id" in payload)

    if len(claimed) > 1:
        return
    if len(claimed) == 1:
        selected = [claimed[0]] if claimed[0]["status"] == "in-progress" else []
    else:
        if scan_root is None or (scan_root / ".scratch").is_symlink():
            return
        local_tasks = read_tasks(scan_root, read_task)
        selected = [task for task in local_tasks if task["status"] == "in-progress"]
    # A Task claimed by another session is not this session's to record.
    foreign = {task["spec"] for task in selected if not claimed and task["session"]}
    fallback = []
    if scan_root is not None and not (scan_root / ".scratch").is_symlink():
        for task in selected:
            scope_value = task["scope_value"]
            scope = (
                task_scope(scan_root, [f"Scope: {scope_value}"])
                if scope_value is not None
                else None
            )
            fallback.append((task["spec"], scope))
    message = legacy_reminder(payload, scan_root, cwd, fallback, foreign)
    if message:
        return output_message(message, "turn_id" in payload)


if __name__ == "__main__":
    try:
        output = main()
        if output is not None:
            os.write(1, (json.dumps(output, ensure_ascii=False) + "\n").encode("utf-8"))
    except Exception:
        pass
