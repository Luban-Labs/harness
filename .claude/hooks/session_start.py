#!/usr/bin/env python3
"""Read Task specs and show the current Task board; hook failures are silent."""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import re
import sys
import tempfile


READY_LIMIT = 5
ACTIVE_LIMIT = 10
OWNER_LIMIT = 8
ARCHIVE_LIMIT = 1000
STATUS = {"ready-for-agent", "in-progress", "done"}
HEADER = re.compile(r"^([^:#：]+)[：:]\s*(.*)$")
CHECK = re.compile(r"^\s*-\s*\[([ xX])\]\s*\[(我|你)\]\s*(.*)$")
NEXT = re.compile(r"(?:^|\|)\s*next[：:]\s*([^|]*)")
BALL = re.compile(r"^(我|你|等)\s*[：:]\s*(.*)$")
STAMP = re.compile(r"^\s*-\s*(\d{2})-(\d{2})\s+(\d{2}):(\d{2})\b")


def project_roots(cwd):
    """Return nearest scan root and main-worktree Task root, if found."""
    cwd = Path(cwd).resolve()
    scan_root = next((p for p in (cwd, *cwd.parents) if (p / ".scratch").is_dir()), None)
    if scan_root is not None and (scan_root / ".scratch").is_symlink():
        return scan_root, None
    task_root = scan_root
    for parent in (cwd, *cwd.parents):
        marker = parent / ".git"
        if marker.is_dir():
            break
        if not marker.is_file():
            continue
        try:
            line = marker.read_text(encoding="utf-8").strip()
            if not line.startswith("gitdir:"):
                break
            gitdir = (parent / line[len("gitdir:"):].strip()).resolve()
            if gitdir.parent.name != "worktrees" or gitdir.parent.parent.name != ".git":
                break
            main = gitdir.parent.parent.parent
            backlink = gitdir / "gitdir"
            commondir = gitdir / "commondir"
            if not gitdir.is_dir() or not backlink.is_file():
                break
            if (gitdir / backlink.read_text(encoding="utf-8").strip()).resolve() != marker.resolve():
                break
            if (commondir.exists() or commondir.is_symlink()) and (
                not commondir.is_file()
                or (gitdir / commondir.read_text(encoding="utf-8").strip()).resolve() != (main / ".git").resolve()
            ):
                break
            scratch = main / ".scratch"
            if scratch.is_dir() and not scratch.is_symlink():
                task_root = main
        except (OSError, UnicodeError, ValueError):
            pass
        break
    return scan_root, task_root


def task_scope(root, value):
    """Validate Scope without letting it escape the Task root."""
    trimmed = value.rstrip("/")
    parts = trimmed.split("/")
    if (not trimmed or value.startswith("/") or "\\" in value
            or any(part in ("", ".", "..") for part in parts)):
        raise ValueError("invalid Scope")
    root = Path(root).resolve()
    path = root.joinpath(*parts).resolve()
    path.relative_to(root)
    if path.exists() and not path.is_dir():
        raise ValueError("Scope is not a directory")
    return "/".join(parts) + "/", path


def read_task(spec, root):
    """Parse one Task. A bad spec raises so callers skip only that Task."""
    spec = Path(spec)
    if spec.is_symlink() or not spec.is_file():
        raise ValueError("invalid spec")
    lines = spec.read_text(encoding="utf-8").splitlines()
    first = re.fullmatch(r"Status[：:]\s*(.*)", lines[0]) if lines else None
    if first is None:
        raise ValueError("missing Status")
    status = first.group(1).strip()
    if status not in STATUS:
        raise ValueError("invalid Status")
    fields = {}
    body = 1
    while body < len(lines) and lines[body].strip() and not lines[body].lstrip().startswith("#"):
        match = HEADER.fullmatch(lines[body])
        if not match or not match.group(1).strip():
            raise ValueError("invalid header")
        key = match.group(1).strip()
        if key in fields or key == "Status":
            raise ValueError("duplicate header")
        fields[key] = match.group(2).strip()
        body += 1
    scope_value = scope = None
    if "Scope" in fields:
        scope_value, scope = task_scope(root, fields["Scope"])
    progress = ""
    checks = []
    section = ""
    for line in lines[body:]:
        if line.startswith("## "):
            section = "checks" if line.startswith("## 验收") else "progress" if line.startswith("## 进展") else ""
        elif line.startswith("# "):
            section = ""
        elif section == "checks":
            match = CHECK.fullmatch(line)
            if match and not re.fullmatch(r"<[^<>]*>", match.group(3).strip()):
                checks.append((match.group(1).lower() == "x", match.group(2), match.group(3).strip()))
        elif section == "progress" and line.strip():
            progress = line.strip()
    next_match = NEXT.search(progress)
    next_text = next_match.group(1).strip() if next_match else ""
    ball_match = BALL.fullmatch(next_text)
    ball = ball_match.group(1) if ball_match else "?"
    if ball_match:
        next_text = ball_match.group(2).strip()
    return {
        "name": spec.parent.name, "status": status, "session": fields.get("会话", ""),
        "scope": scope, "scope_value": scope_value, "progress": progress,
        "ball": ball, "next": next_text, "checks": checks,
        "spec": spec, "mtime_ns": spec.stat().st_mtime_ns,
    }


def session_matches(value, session_id):
    return bool(value and session_id and
                (value == session_id or len(value) >= 8 and session_id.startswith(value)))


def age(task, now):
    moment = None
    match = STAMP.match(task["progress"])
    if match:
        try:
            month, day, hour, minute = map(int, match.groups())
            for year in range(now.year, now.year - 9, -1):
                try:
                    candidate = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue
                if candidate <= now + timedelta(days=1):
                    moment = candidate
                    break
        except ValueError:
            moment = None
    if moment is None:
        moment = datetime.fromtimestamp(task["mtime_ns"] / 1_000_000_000)
    minutes = max(0, int((now - moment).total_seconds() // 60))
    if minutes < 60:
        return f"{minutes} 分钟"
    if minutes < 48 * 60:
        return f"{minutes // 60} 小时"
    return f"{minutes // (24 * 60)} 天"


def load_tasks(root):
    scratch = root / ".scratch"
    if scratch.is_symlink() or not scratch.is_dir():
        return [], [], []
    active, ready, archived = [], [], []
    for path in sorted(scratch.iterdir()):
        if path.name == "archive" or not path.is_dir() or path.is_symlink():
            continue
        try:
            task = read_task(path / "spec.md", root)
        except (OSError, UnicodeError, ValueError):
            continue
        if "\n" in task["name"] or "\r" in task["name"]:
            continue
        if task["status"] == "ready-for-agent":
            ready.append(task["name"])
        else:
            active.append(task)
    archive = scratch / "archive"
    if archive.is_dir() and not archive.is_symlink():
        scanned = 0
        for path in sorted(archive.iterdir()):
            if not path.is_dir() or path.is_symlink() or not (path / "spec.md").exists():
                continue
            scanned += 1
            if scanned > ARCHIVE_LIMIT:
                break
            try:
                task = read_task(path / "spec.md", root)
            except (OSError, UnicodeError, ValueError):
                continue
            if "\n" not in task["name"] and "\r" not in task["name"]:
                archived.append(task)
    return active, ready, archived


def board(root, session_id="", include_session=True):
    active, ready, archived = load_tasks(root)
    owner = [(task, task["next"], False) for task in active
             if task["status"] == "in-progress" and task["ball"] == "你"]
    owner.extend((task, item, True) for task in archived
                 for checked, actor, item in task["checks"]
                 if actor == "你" and not checked)
    if not active and not ready and not owner:
        return ""
    lines = []
    if include_session and session_id:
        lines.append(f"[harness] 本会话 ID: {session_id};开工或接手 Task 时写进它 spec 头部「会话:」行;建 Task 用 python3 .claude/hooks/session_start.py --new-task <名> --kind 功能|记录")
        for task in active:
            if task["status"] == "in-progress" and session_matches(task["session"], session_id):
                lines.append(f"[harness] 本会话认领: {task['name']}(.scratch/{task['name']}/spec.md) 最近进展: {task['progress'] or '无进展'}")
    if owner:
        lines.append(f"[harness] 等你的事 {len(owner)} 条:")
        now = datetime.now()
        for task, item, is_archived in owner[:OWNER_LIMIT]:
            lines.append(f"- {task['name']}(已归档): {item}" if is_archived
                         else f"- {task['name']}: {item}({age(task, now)}前)")
        if len(owner) > OWNER_LIMIT:
            lines.append(f"- 等 {len(owner)} 条")
    if active:
        lines.append(f"[harness] 进行中 Task {len(active)} 个:")
        now = datetime.now()
        for task in active[:ACTIVE_LIMIT]:
            session = f"会话 {task['session'][:8]}" if task["session"] else "无人认领"
            when = f"{age(task, now)}前" if task["progress"] else "无进展"
            mine = [checked for checked, actor, _ in task["checks"] if actor == "我"]
            ball = ("待归档" if task["status"] == "done" else
                    "待结案" if mine and all(mine) else task["ball"])
            lines.append(f"- {task['name']} · {session} · {when} · {ball}: {task['next'][:80]}")
        if len(active) > ACTIVE_LIMIT:
            lines.append(f"- 等 {len(active)} 个")
    if ready:
        shown = ", ".join(ready[:READY_LIMIT])
        more = f" 等 {len(ready)} 个" if len(ready) > READY_LIMIT else ""
        lines.append(f"[harness] 待开工 Task: {shown}{more};需求相关时先读 .scratch/<名>/spec.md")
    return "\n".join(lines)


def template_skeleton(root):
    """Read the first Markdown code block of the project's sole spec template."""
    template = root / ".agents/skills/interview-me/templates/spec.md"
    if not template.is_file():
        raise ValueError("模板文件缺失")
    lines = template.read_text(encoding="utf-8").splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == "```md"), None)
    if start is None:
        raise ValueError("模板没有 ```md 骨架")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].strip() == "```"), None)
    if end is None:
        raise ValueError("模板没有完整的 ```md 骨架")
    return lines[start + 1:end]


def new_task(args):
    if (len(args) not in (4, 6) or args[0] != "--new-task" or args[2] != "--kind"
            or (len(args) == 6 and args[4] != "--cwd")):
        raise ValueError("参数格式应为 --new-task <名> --kind 功能|记录 [--cwd <目录>]")
    name, kind = args[1], args[3]
    if not name or any(char in name for char in "/\\\n\r") or name.startswith(".") or name == "archive":
        raise ValueError("Task 名不合法")
    if kind not in ("功能", "记录"):
        raise ValueError("类型只能是 功能 或 记录")
    cwd = Path(args[5] if len(args) == 6 else os.getcwd())
    if not cwd.is_dir():
        raise ValueError("目录不存在")
    _, root = project_roots(cwd)
    if root is None:
        raise ValueError("找不到 Task 主工作树")
    skeleton = template_skeleton(root)
    sections = []
    current = []
    for line in skeleton:
        if line.startswith("## "):
            sections.append(current)
            current = []
        current.append(line)
    sections.append(current)
    lines = [line for section in sections
             if kind == "功能" or not any(item.strip() == "<!-- 记录可省 -->" for item in section)
             for line in section if line.strip() != "<!-- 记录可省 -->"]
    lines = [f"类型: {kind}" if line == "类型: <功能|记录>" else
             f"# {name}" if line == "# <功能名>" else line for line in lines]
    compact = []
    for line in lines:
        if line or (compact and compact[-1]):
            compact.append(line)
    content = "\n".join(compact).rstrip() + "\n"
    folder = root / ".scratch" / name
    try:
        folder.mkdir()
    except FileExistsError as error:
        raise ValueError("Task 目录已存在") from error
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=folder, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, folder / "spec.md")
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        folder.rmdir()
        raise
    return folder / "spec.md"


def main():
    if "--board" in sys.argv[1:]:
        args = sys.argv[1:]
        if args[0] != "--board" or len(args) not in (1, 3) or (len(args) == 3 and args[1] != "--cwd"):
            return
        cwd = Path(args[2] if len(args) == 3 else os.getcwd())
        if not cwd.is_dir():
            return
        _, root = project_roots(cwd)
        if root:
            output = board(root, include_session=False)
            if output:
                os.write(1, (output + "\n").encode("utf-8"))
        return
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        return
    cwd = payload.get("cwd", os.getcwd())
    session_id = payload.get("session_id", "")
    if not isinstance(cwd, str) or not cwd or not isinstance(session_id, str):
        return
    cwd = Path(cwd)
    if not cwd.is_dir():
        return
    _, root = project_roots(cwd)
    if root is None:
        return
    context = board(root, session_id)
    if context:
        return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}


if __name__ == "__main__":
    if sys.argv[1:] and (sys.argv[1] != "--board" or "--new-task" in sys.argv[2:]):
        try:
            path = new_task(sys.argv[1:])
            print(f"{path} 按模板逐节填写;必填节没内容写「无」")
        except Exception as error:
            print(f"[harness] 建 Task 失败: {error}", file=sys.stderr)
            sys.exit(1)
        sys.exit(0)
    try:
        result = main()
        if result is not None:
            os.write(1, (json.dumps(result, ensure_ascii=False) + "\n").encode("utf-8"))
    except Exception:
        pass
