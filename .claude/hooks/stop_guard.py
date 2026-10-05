#!/usr/bin/env python3
"""Block only when all four progress conditions are known to hold."""

import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timezone


EXCLUDED = {".scratch", ".git", ".claude", ".codex", "node_modules", ".venv",
            "venv", "__pycache__", "dist", "build", ".next", "target"}
TIME = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})"
                  r"(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})?$")
FRAGMENTS = re.compile(r"[=:,\[\]{}]")
GIT_COMMANDS = {"merge", "pull", "checkout", "switch", "rebase", "reset", "stash",
                "cherry-pick", "revert", "am", "apply", "restore"}
GIT_VALUES = {"-C", "-c", "--git-dir", "--work-tree", "--namespace",
              "--super-prefix", "--config-env"}
EDIT_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path",
              "NotebookEdit": "notebook_path"}
COMMAND_TOOLS = {"exec", "exec_command", "shell", "local_shell_call", "write_stdin", "js"}


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


def time_ns(value):
    if not isinstance(value, str):
        return None
    match = TIME.fullmatch(value)
    if match is None:
        return None
    year, month, day, hour, minute, second = map(int, match.group(1, 2, 3, 4, 5, 6))
    try:
        moment = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
        zone = match.group(8)
        offset = 0
        if zone and zone != "Z":
            offset_hour = int(zone[1:3])
            offset_minute = int(zone[4:6])
            if offset_hour > 23 or offset_minute > 59:
                return None
            offset = (offset_hour * 60 + offset_minute) * (1 if zone[0] == "+" else -1)
        delta = moment - datetime(1970, 1, 1, tzinfo=timezone.utc)
        return ((delta.days * 86400 + delta.seconds - offset * 60) * 1_000_000_000
                + int((match.group(7) or "").ljust(9, "0") or "0"))
    except ValueError:
        return None


def candidate_path(value, candidates):
    if not isinstance(value, str):
        return None
    path = Path(value)
    if not path.is_absolute():
        return None
    path = path.resolve()
    return path if path in candidates else None


def shell_words(source):
    events = []
    parts = []
    quoted = False
    pieces = 0

    def flush():
        nonlocal parts, quoted, pieces
        if pieces:
            events.append(("".join(parts), quoted))
        parts, quoted, pieces = [], False, 0

    index = 0
    while index < len(source):
        char = source[index]
        if char in "'\"":
            end = index + 1
            content = []
            while end < len(source) and source[end] not in "\r\n":
                current = source[end]
                if current == char:
                    break
                if char == '"' and current == "\\" and end + 1 < len(source):
                    escaped = source[end + 1]
                    if escaped in "\r\n":
                        break
                    if escaped in '"\\$`':
                        content.append(escaped)
                    else:
                        content.extend(("\\", escaped))
                    end += 2
                else:
                    content.append(current)
                    end += 1
            if end < len(source) and source[end] == char:
                if pieces:
                    quoted = False
                else:
                    quoted = True
                parts.append("".join(content))
                pieces += 1
                index = end + 1
                continue
            flush()
            index += 1
            continue
        if char == "\\" and index + 1 < len(source) and source[index + 1] not in "\r\n":
            parts.append(source[index + 1])
            quoted = False
            pieces += 1
            index += 2
            continue
        if char in "\r\n;|&()<>" or char.isspace():
            flush()
            if char in "\r\n;|&()" and not (char == "&" and source[index:index + 2] == "&>"):
                events.append(None)
            index += 2 if source[index:index + 2] == "&>" else 1
            continue
        parts.append(char)
        if quoted:
            quoted = False
        pieces += 1
        index += 1
    flush()
    return events


def js_literals(source):
    literals = []
    index = 0
    while index < len(source):
        if source.startswith("//", index):
            index += 2
            while index < len(source) and source[index] not in "\r\n":
                index += 1
            continue
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            index = len(source) if end < 0 else end + 2
            continue
        quote = source[index]
        if quote not in "'\"`":
            index += 1
            continue
        end = index + 1
        content = []
        while end < len(source) and (quote == "`" or source[end] not in "\r\n"):
            char = source[end]
            if char == quote:
                break
            if char == "\\" and end + 1 < len(source):
                escaped = source[end + 1]
                if escaped == "u" and end + 5 < len(source):
                    digits = source[end + 2:end + 6]
                    if all(digit in "0123456789abcdefABCDEF" for digit in digits):
                        content.append(chr(int(digits, 16)))
                        end += 6
                        continue
                if escaped in "'\"`\\nt":
                    content.append({"n": "\n", "t": "\t"}.get(escaped, escaped))
                    end += 2
                    continue
                content.extend(("\\", escaped))
                end += 2
                continue
            content.append(char)
            end += 1
        if end < len(source) and source[end] == quote:
            literals.append("".join(content))
            index = end + 1
        else:
            index += 1
    return literals


def json_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from json_strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from json_strings(nested)


def git_evidence(events):
    for index, event in enumerate(events):
        if event is None or event[0].rstrip("/").rsplit("/", 1)[-1] != "git":
            continue
        cursor = index + 1
        while cursor < len(events) and events[cursor] is not None:
            word = events[cursor][0]
            if word.startswith("-"):
                if word in GIT_VALUES:
                    if cursor + 1 >= len(events) or events[cursor + 1] is None:
                        break
                    cursor += 2
                else:
                    cursor += 1
                continue
            if word in GIT_COMMANDS:
                return True
            break
    return False


def command_evidence(command, start, end, candidates):
    names = {path.name for path, mtime in candidates.items()
             if start <= mtime <= end + 1_000_000}
    if not names:
        return False
    sources = [shell_words(command)] if isinstance(command, str) else command
    if not isinstance(sources, list):
        return False
    for events in sources:
        if git_evidence(events):
            return True
        for event in events:
            if event is None:
                continue
            word, quoted = event
            parts = (word,) if quoted else FRAGMENTS.split(word)
            if any(part.rstrip("/").rsplit("/", 1)[-1] in names for part in parts):
                return True
    return False


def codex_command(payload):
    kind = payload.get("type")
    if kind == "local_shell_call":
        action = payload.get("action")
        command = action.get("command") if isinstance(action, dict) else None
        if isinstance(command, list) and all(isinstance(part, str) for part in command):
            return [[(part, True) for part in command]] + [shell_words(part) for part in command]
        return None
    if kind not in ("custom_tool_call", "function_call"):
        return None
    if payload.get("name") not in COMMAND_TOOLS:
        return None
    key = "input" if kind == "custom_tool_call" else "arguments"
    raw = payload.get(key)
    if not isinstance(raw, str):
        return None
    if kind == "function_call":
        try:
            return [shell_words(value) for value in json_strings(json.loads(raw))]
        except ValueError:
            return [shell_words(raw)]
    if payload.get("name") == "exec":
        literals = js_literals(raw)
        return [shell_words(value) for value in literals] if literals else [shell_words(raw)]
    return [shell_words(raw)]


def transcript_evidence(path, spec_mtime, candidates):
    if path.stat().st_mtime_ns <= spec_mtime:
        return False
    claude_calls = {}
    claude_results = {}
    codex_calls = {}
    codex_results = {}
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if not any(token in line for token in ('"tool_use"', '"tool_result"',
                                                  '"call_id"', '"FileChange"')):
                continue
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if not isinstance(row, dict):
                continue
            stamp = time_ns(row.get("timestamp"))
            if stamp is None:
                continue
            if row.get("type") in ("assistant", "user"):
                message = row.get("message")
                content = message.get("content") if isinstance(message, dict) else None
                if not isinstance(content, list):
                    continue
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    if row["type"] == "assistant" and item.get("type") == "tool_use":
                        call_id = item.get("id")
                        if not isinstance(call_id, str):
                            continue
                        name = item.get("name")
                        data = item.get("input")
                        if name in EDIT_TOOLS and isinstance(data, dict):
                            claude_calls[call_id] = ("edit", data.get(EDIT_TOOLS[name]), stamp)
                        elif name == "Bash" and isinstance(data, dict):
                            claude_calls[call_id] = ("command", data.get("command"), stamp)
                    elif row["type"] == "user" and item.get("type") == "tool_result":
                        call_id = item.get("tool_use_id")
                        if isinstance(call_id, str):
                            claude_results[call_id] = (stamp, item.get("is_error") is not True)
            payload = row.get("payload")
            if not isinstance(payload, dict):
                continue
            if row.get("type") == "event_msg" and payload.get("type") == "item_completed":
                item = payload.get("item")
                completed = payload.get("completed_at_ms")
                if (isinstance(item, dict) and item.get("type") == "FileChange"
                        and not isinstance(completed, bool)
                        and isinstance(completed, (int, str))):
                    try:
                        completed_ns = int(completed) * 1_000_000
                    except ValueError:
                        continue
                    changes = item.get("changes")
                    if completed_ns > spec_mtime and isinstance(changes, dict):
                        if any(candidate_path(change, candidates) is not None for change in changes):
                            return True
            kind = payload.get("type")
            call_id = payload.get("call_id")
            if not isinstance(call_id, str):
                continue
            command = codex_command(payload)
            if command is not None:
                codex_calls[call_id] = (command, stamp)
            elif kind in ("custom_tool_call_output", "function_call_output"):
                codex_results[call_id] = stamp
    for call_id, (kind, value, start) in claude_calls.items():
        result = claude_results.get(call_id)
        if result is None:
            continue
        end, success = result
        if kind == "edit":
            if success and end > spec_mtime and candidate_path(value, candidates) is not None:
                return True
        elif command_evidence(value, start, end, candidates):
            return True
    return any(command_evidence(command, start, codex_results[call_id], candidates)
               for call_id, (command, start) in codex_calls.items()
               if call_id in codex_results)


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
    if scratch.is_symlink():
        return
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
    candidates = {}
    count = 0
    for directory, dirs, files in os.walk(
            root if scope is None else scope, onerror=walk_error, followlinks=False):
        dirs[:] = [entry for entry in dirs
                   if entry not in EXCLUDED and not (Path(directory) / entry).is_symlink()]
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
    if not isinstance(transcript, str) or not transcript or not Path(transcript).is_file():
        return
    transcript = Path(transcript)
    sources = [transcript]
    subagents = transcript.with_suffix("") / "subagents"
    if subagents.is_dir():
        sources.extend(subagents.rglob("*.jsonl"))
    if any(transcript_evidence(source, spec_mtime, candidates) for source in sources):
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
