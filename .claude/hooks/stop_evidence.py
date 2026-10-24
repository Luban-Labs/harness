#!/usr/bin/env python3
"""Find direct evidence in Claude and Codex transcripts that this session changed a file."""

import json
from pathlib import Path
import re
from datetime import datetime, timezone


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


def edited_paths(path):
    """Collect absolute paths written by successful edit tools or Codex FileChange."""
    calls = {}
    done = set()
    edited = set()
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if not any(token in line for token in ('"tool_use"', '"tool_result"', '"FileChange"')):
                continue
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if not isinstance(row, dict):
                continue
            message = row.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            for item in content if isinstance(content, list) else ():
                if not isinstance(item, dict):
                    continue
                if row.get("type") == "assistant" and item.get("type") == "tool_use":
                    data = item.get("input")
                    name = item.get("name")
                    key = EDIT_TOOLS.get(name) if isinstance(name, str) else None
                    if key and isinstance(data, dict) and isinstance(item.get("id"), str):
                        calls[item["id"]] = data.get(key)
                elif (row.get("type") == "user" and item.get("type") == "tool_result"
                      and item.get("is_error") is not True
                      and isinstance(item.get("tool_use_id"), str)):
                    done.add(item["tool_use_id"])
            payload = row.get("payload")
            if (isinstance(payload, dict) and row.get("type") == "event_msg"
                    and payload.get("type") == "item_completed"):
                item = payload.get("item")
                if (isinstance(item, dict) and item.get("type") == "FileChange"
                        and isinstance(item.get("changes"), dict)):
                    edited.update(change for change in item["changes"] if isinstance(change, str))
    edited.update(value for call_id, value in calls.items()
                  if call_id in done and isinstance(value, str))
    return {Path(value).resolve() for value in edited if Path(value).is_absolute()}


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
