#!/usr/bin/env python3
"""Read Task specs and show the current Task board; hook failures are silent."""

import json
import math
import os
from datetime import datetime, timedelta
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


READY_LIMIT = 5
ACTIVE_LIMIT = 10
OWNER_LIMIT = 8
MISSING_CONCEPT_LIMIT = 3
ARCHIVE_LIMIT = 1000
STATUS = {"ready-for-agent", "in-progress", "done"}
HEADER = re.compile(r"^([^:#：]+)[：:]\s*(.*)$")
CHECK = re.compile(r"^\s*-\s*\[([ xX])\]\s*\[(我|你)\]\s*(.*)$")
NEXT = re.compile(r"(?:^|\|)\s*next[：:]\s*([^|]*)")
BALL = re.compile(r"^(我|你|等)\s*[：:]\s*(.*)$")
STAMP = re.compile(r"^\s*-\s*(\d{2})-(\d{2})\s+(\d{2}):(\d{2})\b")
FENCE = re.compile(r"\s*(`{3,}|~{3,})")
CORE_TABLE = "docs/rules/core-judgments.md"
DSH_SESSION = re.compile(r"session-[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z")


def main_worktree(root):
    """Return a backlink-verified main worktree for a .git file root."""
    root = Path(root).resolve()
    marker = root / ".git"
    if not marker.is_file():
        return None
    try:
        line = marker.read_text(encoding="utf-8").strip()
        if not line.startswith("gitdir:"):
            return None
        gitdir = (root / line[len("gitdir:"):].strip()).resolve()
        if gitdir.parent.name != "worktrees" or gitdir.parent.parent.name != ".git":
            return None
        main = gitdir.parent.parent.parent
        backlink = gitdir / "gitdir"
        commondir = gitdir / "commondir"
        if not gitdir.is_dir() or not backlink.is_file():
            return None
        if (gitdir / backlink.read_text(encoding="utf-8").strip()).resolve() != marker.resolve():
            return None
        if (commondir.exists() or commondir.is_symlink()) and (
            not commondir.is_file()
            or (gitdir / commondir.read_text(encoding="utf-8").strip()).resolve() != (main / ".git").resolve()
        ):
            return None
        return main
    except (OSError, UnicodeError, ValueError):
        return None


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
        main = main_worktree(parent)
        if main is not None:
            scratch = main / ".scratch"
            if scratch.is_dir() and not scratch.is_symlink():
                task_root = main
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


def spec_sections(lines):
    """List (line index, title, body) per `## ` heading; a body runs to the next `## ` or `# ` heading."""
    sections = []
    body = None
    for index, line in enumerate(lines):
        if line.startswith("## "):
            body = []
            sections.append((index, line[3:].strip(), body))
        elif line.startswith("# "):
            body = None
        elif body is not None:
            body.append(line)
    return sections


def section_lines(sections, name):
    """Non-blank lines of every section whose title starts with name, in order."""
    return [line for _, title, body in sections if title.startswith(name) for line in body if line.strip()]


def ready_to_close(task):
    """待结案: the Task has [我] checks and every one is ticked."""
    mine = [checked for checked, actor, _ in task["checks"] if actor == "我"]
    return bool(mine) and all(mine)


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
    sections = spec_sections(lines[body:])
    checks = []
    for line in section_lines(sections, "验收"):
        match = CHECK.fullmatch(line)
        if match and not re.fullmatch(r"<[^<>]*>", match.group(3).strip()):
            checks.append((match.group(1).lower() == "x", match.group(2), match.group(3).strip()))
    progress_lines = section_lines(sections, "进展")
    progress = progress_lines[-1].strip() if progress_lines else ""
    takeovers = [line for line in progress_lines if "接手自 " in line]
    next_match = NEXT.search(progress)
    next_text = next_match.group(1).strip() if next_match else ""
    ball_match = BALL.fullmatch(next_text)
    ball = ball_match.group(1) if ball_match else "?"
    if ball_match:
        next_text = ball_match.group(2).strip()
    return {
        "name": spec.parent.name, "status": status, "session": fields.get("会话", ""),
        "kind": fields.get("类型", ""),
        "scope": scope, "scope_value": scope_value, "progress": progress,
        "takeovers": takeovers,
        "ball": ball, "next": next_text, "checks": checks,
        "spec": spec, "mtime_ns": spec.stat().st_mtime_ns,
    }


def task_at(folder, root):
    """Return the Task a .scratch folder holds, or None when the folder is not a Task."""
    if not folder.is_dir() or folder.is_symlink():
        return None
    try:
        task = read_task(folder / "spec.md", root)
    except (OSError, UnicodeError, ValueError):
        return None
    if "\n" in task["name"] or "\r" in task["name"]:
        return None
    return task


def read_tasks(root):
    """Return the Tasks directly under .scratch (not archived), by folder name."""
    scratch = Path(root) / ".scratch"
    if scratch.is_symlink() or not scratch.is_dir():
        return []
    return [task for folder in sorted(scratch.iterdir())
            if folder.name != "archive" and (task := task_at(folder, root)) is not None]


def session_matches(value, session_id):
    if not isinstance(value, str) or not isinstance(session_id, str) or not value or not session_id:
        return False
    if DSH_SESSION.fullmatch(session_id):
        return bool(re.match(r"session-[0-9a-fA-F]{8}", value) and
                    session_id.startswith(value))
    return value == session_id or len(value) >= 8 and session_id.startswith(value)


def session_short(value):
    """Keep DSH's host marker and eight UUID digits in displayed claims."""
    return value[:16] if re.match(r"session-[0-9a-fA-F]{8}(?:-|$)", value) else value[:8]


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
    for task in read_tasks(root):
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
            task = task_at(path, root)
            if task is not None:
                archived.append(task)
    return active, ready, archived


def core_judgment_entries(root, deadline=None):
    """Read unfenced concepts and backticked project-relative path:name implementations."""
    root = Path(root).resolve()
    entries = []
    current = None
    fence = ""
    try:
        with (root / CORE_TABLE).open(encoding="utf-8") as stream:
            for line in stream:
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError("responsibility table scan ran out of time")
                match = FENCE.match(line)
                if fence:
                    if match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence) \
                            and not line.strip().strip(fence[0]):
                        fence = ""
                elif match:
                    fence = match.group(1)
                elif line.startswith("## ") and line[3:].strip():
                    current = (line[3:].strip(), [])
                    entries.append(current)
                elif line.startswith("# "):
                    current = None
                elif current is not None and re.match(r"^\s*-\s*唯一实现\s*[:：]", line):
                    for reference in re.findall(r"`([^`\r\n]+)`", line):
                        relative, colon, name = reference.rpartition(":")
                        if (not colon or not relative or Path(relative).is_absolute() or "\\" in relative
                                or any(part in ("", ".", "..") for part in relative.split("/"))
                                or not all(char.isprintable() for char in relative)
                                or not re.fullmatch(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*", name)):
                            continue
                        if (root / relative).resolve().is_relative_to(root):
                            current[1].append((relative, name))
    except TimeoutError:
        raise
    except (OSError, UnicodeError, ValueError):
        return []
    return entries


def core_judgments(root):
    """List concepts and missing implementation paths; failures drop only this optional line."""
    try:
        from stop_evidence import shown

        entries = core_judgment_entries(root)
        if not entries:
            return ""
        names = "、".join(shown(name) for name, _ in entries)
        missing = []
        for name, implementations in entries:
            for relative, _ in implementations:
                try:
                    (Path(root) / relative).stat()
                except (FileNotFoundError, NotADirectoryError):
                    missing.append(name)
                    break
        result = f"[harness] 核心判断表 {CORE_TABLE}:{names};设计前先读 docs/rules/architecture.md 总图并查本表"
        if missing:
            more = f" 等 {len(missing)} 个" if len(missing) > MISSING_CONCEPT_LIMIT else ""
            result += ";唯一实现路径找不到:" + "、".join(shown(name) for name in missing[:MISSING_CONCEPT_LIMIT]) + more
        return result
    except Exception:
        return ""


def record_stamp(claim, kind, probe):
    """Index each record tree once, then resolve full or prefix claims."""
    if kind not in probe["indexes"]:
        index = {}
        if kind == "dsh":
            for row in probe.get("dsh_session_records", ()):
                if time.monotonic() >= probe["deadline"]:
                    break
                if not isinstance(row, dict) or row.get("parent_session_id") is not None:
                    continue
                session_id, stamp = row.get("session_id"), row.get("mtime")
                if (isinstance(session_id, str) and DSH_SESSION.fullmatch(session_id)
                        and type(stamp) in (int, float) and math.isfinite(stamp) and stamp > 0):
                    index[session_id] = max(index.get(session_id, 0), stamp)
        else:
            root = probe["home"] / (".claude/projects" if kind == "claude" else ".codex/sessions")
            pattern = "*/*.jsonl" if kind == "claude" else "**/rollout-*.jsonl"
            try:
                for path in root.glob(pattern):
                    if time.monotonic() >= probe["deadline"]:
                        break
                    match = (re.search(r"([0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})\.jsonl$", path.name)
                             if kind == "codex" else None)
                    session_id = match.group(1) if match else path.stem if kind == "claude" else ""
                    if re.fullmatch(r"[A-Za-z0-9_-]{8,}", session_id):
                        try:
                            index[session_id] = max(index.get(session_id, 0), path.stat().st_mtime)
                        except OSError:
                            pass
            except (OSError, ValueError):
                pass
        probe["indexes"][kind] = index
    stamp = None
    for session_id, candidate in probe["indexes"][kind].items():
        if time.monotonic() >= probe["deadline"]:
            return None
        if session_matches(claim, session_id):
            if kind == "dsh" and stamp is not None:
                return None  # A short claim resolving to two top-level sessions is unknown.
            stamp = max(stamp or 0, candidate)
    return stamp


def claim_state(claim, probe):
    cache = probe["states"]
    if claim in cache:
        return cache[claim]
    cache[claim] = ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,}", claim) or time.monotonic() >= probe["deadline"]:
        return ""
    now = probe["now"]
    def hours(stamp):
        count = max(0, int((now - stamp) // 3600))
        return f"{count} 小时" if count else "不到 1 小时"

    if probe["dsh_host"] and re.match(r"session-[0-9a-fA-F]{8}", claim):
        stamp = record_stamp(claim, "dsh", probe)
        if stamp is not None and time.monotonic() < probe["deadline"]:
            cache[claim] = "在做" if now - stamp < 36000 else f"断了 {hours(stamp)}"
        return cache[claim]

    matching = [row for row in probe["registrations"]
                if session_matches(claim, row.get("sessionId"))]
    confirmed_dead = bool(matching) or probe["valid_registrations"] > 0
    uncertain = False
    for row in matching:
        pid, start = row.get("pid"), row.get("procStart")
        if type(pid) is not int or pid <= 0 or not isinstance(start, str) or not start:
            uncertain = True
            continue
        if time.monotonic() >= probe["deadline"]:
            return ""
        if pid not in probe["processes"]:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                probe["processes"][pid] = (False, None)
            except (OSError, OverflowError):
                probe["processes"][pid] = (None, None)
            else:
                remaining = probe["deadline"] - time.monotonic()
                if remaining <= 0:
                    return ""
                try:
                    result = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)],
                                            capture_output=True, text=True, timeout=min(1, remaining),
                                            env={**os.environ, "TZ": "UTC", "LC_ALL": "C"})
                    probe["processes"][pid] = (True, result.stdout.strip() or None)
                except (OSError, subprocess.TimeoutExpired):
                    probe["processes"][pid] = (True, None)
        exists, actual_start = probe["processes"][pid]
        if exists is True and actual_start == start:
            stamp = record_stamp(row["sessionId"], "claude", probe)
            updated = row.get("updatedAt")
            stamp = stamp if stamp is not None else updated / 1000 if type(updated) is int and updated > 0 else now
            if time.monotonic() < probe["deadline"]:
                cache[claim] = "在做" if now - stamp < 36000 else f"挂着 {hours(stamp)}"
            return cache[claim]
        if exists is None or exists is True and actual_start is None:
            uncertain = True
    claude = record_stamp(claim, "claude", probe)
    if time.monotonic() >= probe["deadline"]:
        return ""
    if confirmed_dead and not uncertain and claude is not None:
        cache[claim] = f"断了 {hours(claude)}"
    elif not matching or uncertain:
        stamp = claude if claude is not None else record_stamp(claim, "codex", probe)
        if stamp is not None and time.monotonic() < probe["deadline"]:
            cache[claim] = ("在做" if now - stamp < 36000 else
                            f"断了 {hours(stamp)}")
    return cache[claim]


def owner_items(active, archived):
    """等你的事: in-progress Tasks whose ball is 你, then unchecked [你] items of archived Tasks."""
    items = [(task, task["next"], False) for task in active
             if task["status"] == "in-progress" and task["ball"] == "你"]
    items.extend((task, item, True) for task in archived
                 for checked, actor, item in task["checks"]
                 if actor == "你" and not checked)
    return items


def task_ball(task):
    return ("待归档" if task["status"] == "done" else
            "待结案" if ready_to_close(task) else task["ball"])


def claim_states(tasks, *, dsh_session_records=(), dsh_host=False):
    """Each Task's claim state within one 3-second probe; "" when unclaimed or unknown."""
    clock = time.time()
    deadline = time.monotonic() + 3
    try:
        home = Path.home()
    except Exception:
        home = None
    registrations = []
    valid = 0
    if home and any(task["status"] == "in-progress" and task["session"] for task in tasks):
        try:
            for path in (home / ".claude/sessions").glob("*.json"):
                if time.monotonic() >= deadline:
                    break
                try:
                    entry = json.loads(path.read_text(encoding="utf-8"))
                    session_id = entry.get("sessionId") if isinstance(entry, dict) else None
                    if isinstance(session_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{8,}", session_id):
                        registrations.append(entry)
                        if type(entry.get("pid")) is int and entry["pid"] > 0 and isinstance(entry.get("procStart"), str) and entry["procStart"]:
                            valid += 1
                except (OSError, UnicodeError, ValueError):
                    continue
        except (OSError, ValueError):
            pass
    probe = {"home": home, "now": clock, "deadline": deadline,
             "registrations": registrations, "valid_registrations": valid,
             "indexes": {}, "processes": {}, "states": {},
             "dsh_session_records": dsh_session_records, "dsh_host": dsh_host}
    states = []
    for task in tasks:
        state = ""
        if home and time.monotonic() < deadline and task["status"] == "in-progress" and task["session"]:
            try:
                state = claim_state(task["session"], probe)
            except Exception:
                pass
        states.append(state)
    return states


def active_rows(tasks, states, now):
    """Each active Task as the board shows it; the text board and the JSON both draw these rows."""
    return [{"name": task["name"], "status": task["status"], "ball": task_ball(task), "next": task["next"],
             "session": session_short(task["session"]) if task["session"] else "",
             "session_state": state, "session_kind": state.split(" ", 1)[0],
             "age": age(task, now) if task["progress"] else None}
            for task, state in zip(tasks, states)]


def owner_rows(items, now):
    return [{"task": task["name"], "item": item, "archived": is_archived,
             "age": None if is_archived else age(task, now)}
            for task, item, is_archived in items]


def board_json(root, *, dsh_session_records=(), dsh_host=False):
    """The whole board as data, nothing capped, for tools such as the task-board pane mod.

    The pane reads version 1: renaming or dropping a field breaks it, so bump the version.
    """
    active, ready, archived = load_tasks(root)
    now = datetime.now()
    states = claim_states(active, dsh_session_records=dsh_session_records, dsh_host=dsh_host)
    return {"version": 1, "project": Path(root).name, "owner": owner_rows(owner_items(active, archived), now),
            "active": active_rows(active, states, now), "ready": ready}


def board(root, session_id="", include_session=True, *, dsh_session_records=(),
          allow_own=True, dsh_host=False):
    active, ready, archived = load_tasks(root)
    owner = owner_items(active, archived)
    if not active and not ready and not owner:
        return ""
    lines = []
    if include_session and session_id:
        session_line = f"[harness] 本会话 ID: {session_id}"
        if allow_own:
            session_line += ";开工或接手 Task 时写进它 spec 头部「会话:」行;建 Task 用 python3 .claude/hooks/session_start.py --new-task <名> --kind 功能|记录"
        lines.append(session_line)
        for task in active:
            if (allow_own and task["status"] == "in-progress" and task["session"]
                    and not session_matches(task["session"], session_id)
                    and any(session_matches(match.group(1), session_id)
                            for row in task["takeovers"]
                            if (match := re.search(r"接手自\s+([A-Za-z0-9_-]+)", row)))):
                lines.append(f"[harness] 你认领过的 Task {task['name']} 已被会话 {session_short(task['session'])} 接手:别再改它的 spec 与代码;有话发消息给新会话(Claude 用 ListAgents),发不了就告诉 owner。")
        for task in active:
            if allow_own and task["status"] == "in-progress" and session_matches(task["session"], session_id):
                lines.append(f"[harness] 本会话认领: {task['name']}(.scratch/{task['name']}/spec.md) 最近进展: {task['progress'] or '无进展'}")
    if owner:
        lines.append(f"[harness] 等你的事 {len(owner)} 条:")
        now = datetime.now()
        for row in owner_rows(owner[:OWNER_LIMIT], now):
            lines.append(f"- {row['task']}(已归档): {row['item']}" if row["archived"]
                         else f"- {row['task']}: {row['item']}({row['age']}前)")
        if len(owner) > OWNER_LIMIT:
            lines.append(f"- 等 {len(owner)} 条")
    if active:
        lines.append(f"[harness] 进行中 Task {len(active)} 个:")
        now = datetime.now()
        shown = active[:ACTIVE_LIMIT]
        states = claim_states(shown, dsh_session_records=dsh_session_records, dsh_host=dsh_host)
        for row in active_rows(shown, states, now):
            session = f"会话 {row['session']}" if row["session"] else "无人认领"
            if row["session_state"]:
                session += f"({row['session_state']})"
            when = f"{row['age']}前" if row["age"] else "无进展"
            lines.append(f"- {row['name']} · {session} · {when} · {row['ball']}: {row['next'][:80]}")
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
        as_json = args[1:2] == ["--json"]
        rest = args[2:] if as_json else args[1:]
        if args[0] != "--board" or rest and (len(rest) != 2 or rest[0] != "--cwd"):
            return
        cwd = Path(rest[1] if rest else os.getcwd())
        if not cwd.is_dir():
            return
        _, root = project_roots(cwd)
        if root:
            dsh_host = os.environ.get("HARNESS_HOST") == "dsh"
            output = (json.dumps(board_json(root, dsh_host=dsh_host), ensure_ascii=False) if as_json
                      else board(root, include_session=False, dsh_host=dsh_host))
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
    is_dsh = os.environ.get("HARNESS_HOST") == "dsh"
    allow_own = not is_dsh or (
        "dsh_parent_session_id" in payload and payload["dsh_parent_session_id"] is None
        and DSH_SESSION.fullmatch(session_id) is not None
    )
    records = payload.get("dsh_session_records", ()) if is_dsh else ()
    context = board(root, session_id, dsh_session_records=records if isinstance(records, list) else (),
                    allow_own=allow_own, dsh_host=is_dsh)
    if context:
        # Only an already non-empty board carries the concept line: no Task, no bytes.
        concepts = core_judgments(root)
        if concepts:
            context += "\n" + concepts
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
