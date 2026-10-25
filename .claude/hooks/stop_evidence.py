#!/usr/bin/env python3
"""Find direct evidence in Claude and Codex transcripts that this session changed a file."""

import json
import os
from pathlib import Path
import re
import time
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



def shown(text):
    """Escape control and line-break characters so text echoed from a repo or record stays inside its one reminder line."""
    return "".join(char if char.isprintable() else repr(char)[1:-1] for char in text)


def excluded_dir(name):
    """Whether a directory holds no project code: the Task area, VCS, agent config, dependencies or build output."""
    return name in EXCLUDED

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


def edited_paths(path, tail=None):
    """Collect absolute paths written by successful edit tools or Codex FileChange.

    With tail, read only the last that many bytes, starting at the next full line.
    """
    edited = set()
    for _, tool, data in successful_edits(path, tail)[0]:
        if tool == "FileChange":
            edited.update(change for change in data if isinstance(change, str))
        elif isinstance(data.get(EDIT_TOOLS[tool]), str):
            edited.add(data[EDIT_TOOLS[tool]])
    return {Path(value).resolve() for value in edited if Path(value).is_absolute()}


def session_records(transcript):
    """List this session's records: the Stop input transcript, then every subagent record beside it."""
    transcript = Path(transcript)
    subagents = transcript.with_suffix("") / "subagents"
    return [transcript, *(sorted(subagents.rglob("*.jsonl")) if subagents.is_dir() else ())]


def dsh_host():
    return os.environ.get("HARNESS_HOST") == "dsh"


def evidence_sources(payload):
    if dsh_host():
        return dsh_session_records(payload)
    transcript = payload.get("transcript_path")
    if not isinstance(transcript, str) or not transcript or not Path(transcript).is_file():
        return []
    return session_records(transcript)


def turn_boundary(row):
    """True for a turn boundary, None for an invalid DSH start, otherwise False.

    Claude writes stop_hook_summary and turn_duration once a turn ends, after its Stop hooks ran;
    messages that arrive mid-turn (user, task notification, peer) are rows inside the turn.
    DSH starts a turn explicitly and carries a stable seq/turn pair plus millisecond time.
    """
    if row.get("type") == "turn/start":
        data = row.get("data")
        seq = row.get("seq")
        stamp = row.get("time")
        turn = data.get("turn") if isinstance(data, dict) else None
        return (True if all(type(value) is int and value >= 0 for value in (seq, stamp, turn))
                else None)
    if row.get("type") == "event_msg":
        payload = row.get("payload")
        return isinstance(payload, dict) and payload.get("type") == "task_started"
    return row.get("type") == "system" and row.get("subtype") in ("stop_hook_summary", "turn_duration")


def successful_edits(path, tail=None, turn=False, deadline=None):
    """List (timestamp ns, tool, input) of successful edits in call order, and when the turn began.

    A Claude edit tool counts once its result comes back without is_error; a Codex
    item_completed FileChange counts as ("FileChange", changes). With tail, read only the
    last that many bytes, starting at the next full line. With turn, keep only the edits
    after the last turn boundary and return its timestamp (the first one read when the tail
    holds no boundary); without turn the second value is None. Past a monotonic deadline,
    raise TimeoutError.
    """
    tokens = ('"tool_use"', '"tool_result"', '"FileChange"') + (
        ('"stop_hook_summary"', '"turn_duration"', '"task_started"') if turn else ())
    calls = {}
    done = set()
    order = []
    start = None
    with path.open("rb") as stream:
        size = path.stat().st_size
        if tail is not None and size > tail:
            stream.seek(size - tail)
            stream.readline()
        for count, raw in enumerate(stream):
            if deadline is not None and count % 1024 == 0 and time.monotonic() >= deadline:
                raise TimeoutError("transcript scan ran out of time")
            line = raw.decode("utf-8", errors="replace")
            # Until a turn has a start, the first readable row supplies it.
            if not any(token in line for token in tokens) and not (turn and start is None):
                continue
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if not isinstance(row, dict):
                continue
            stamp = time_ns(row.get("timestamp"))
            if turn:
                if turn_boundary(row):
                    order = []
                    start = stamp
                elif start is None:
                    start = stamp
            message = row.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            for item in content if isinstance(content, list) else ():
                if not isinstance(item, dict):
                    continue
                if row.get("type") == "assistant" and item.get("type") == "tool_use":
                    data = item.get("input")
                    name = item.get("name")
                    if (isinstance(name, str) and name in EDIT_TOOLS and isinstance(data, dict)
                            and isinstance(item.get("id"), str)):
                        calls[item["id"]] = (stamp, name, data)
                        order.append(item["id"])
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
                    order.append((stamp, "FileChange", item["changes"]))
    # A call id seen twice keeps its last input, listed once where it was first called.
    listed = set()
    edits = []
    for entry in order:
        if isinstance(entry, tuple):
            edits.append(entry)
        elif entry in done and entry not in listed:
            listed.add(entry)
            edits.append(calls[entry])
    return edits, (start if turn else None)


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


DSH_EXIT = re.compile(r"\[exit code: (-?\d+)\]\s*$")
DSH_TERMINATED = re.compile(
    r"(?m)^\[(?:timed out after \d+ms|stopped: [^\n]*|killed by signal: [^\n]*|sandbox: [^\n]*)\]"
    r"(?:\n\[[^\n]*\])*\s*$"
)


def dsh_records(path, tail=None, deadline=None):
    """Read complete appended v4 zstd frames; reject damaged logs and unsupported runtimes."""
    from compression import zstd  # Python 3.14; ImportError leaves evidence reminders silent.

    raw = Path(path).read_bytes()
    view = memoryview(raw)
    spans = []
    offset = 0
    while offset < len(view):
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("DSH transcript scan ran out of time")
        size = zstd.get_frame_size(view[offset:])
        if size <= 0 or offset + size > len(view):
            raise ValueError("incomplete DSH frame")
        spans.append((offset, size))
        offset += size
    if not spans:
        raise ValueError("empty DSH transcript")
    for index, (offset, size) in enumerate(spans):
        if index and tail is not None and offset + size < len(view) - tail:
            continue
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("DSH transcript scan ran out of time")
        data = zstd.decompress(view[offset:offset + size]).decode("utf-8")
        for line in data.splitlines():
            if line:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("invalid DSH record")
                yield row


def dsh_header(path):
    row = next(dsh_records(path, tail=0), None)
    if (not isinstance(row, dict) or row.get("type") != "session"
            or row.get("version") != 4 or not isinstance(row.get("id"), str)):
        raise ValueError("unsupported DSH transcript")
    return row


def dsh_session_records(payload):
    """The dispatcher-selected parent and only its descendants, checked by v4 headers."""
    value = payload.get("dsh_transcript_path")
    if not isinstance(value, str) or not value:
        return []
    main = Path(value)
    header = dsh_header(main)
    if header["id"] != payload.get("session_id"):
        return []
    children = payload.get("dsh_child_transcript_paths", [])
    if not isinstance(children, list):
        return [main]
    pending = {}
    for value in children:
        if not isinstance(value, str) or not value:
            continue
        path = Path(value)
        try:
            child = dsh_header(path)
        except (OSError, ValueError, ImportError):
            continue
        parent = child.get("parentSession")
        if isinstance(parent, str) and parent:
            pending[path] = (child["id"], parent)
    selected = [main]
    ids = {header["id"]}
    while pending:
        added = False
        for path, (child_id, parent) in list(pending.items()):
            if parent in ids:
                selected.append(path)
                ids.add(child_id)
                del pending[path]
                added = True
        if not added:
            break
    return selected


def dsh_calls(path, tail=None, turn=False, deadline=None):
    """Return successful edit and command calls, plus the latest turn start, from one DSH log."""
    header = None
    calls = {}
    results = {}
    registered = set()
    settled = {}
    order = []
    turn_start = None
    for row in dsh_records(path, tail=tail, deadline=deadline):
        kind = row.get("type")
        if header is None:
            if kind != "session" or row.get("version") != 4:
                raise ValueError("unsupported DSH transcript")
            header = row
            continue
        data = row.get("data")
        if kind == "turn/start" and turn_boundary(row) is not True:
            raise ValueError("invalid DSH turn start")
        if not isinstance(data, dict):
            continue
        stamp = row.get("time")
        stamp = stamp * 1_000_000 if isinstance(stamp, int) and not isinstance(stamp, bool) else None
        if kind == "turn/start":
            turn_start = stamp
            if turn:
                order = []
        elif kind == "tool/call" and "surfaceOp" not in row:
            call_id = data.get("callId")
            name = data.get("name")
            if not isinstance(call_id, str) or name not in ("write", "edit", "multi_edit", "notebook_edit", "bash"):
                continue
            arguments = data.get("arguments")
            try:
                arguments = json.loads(arguments) if isinstance(arguments, str) else arguments
            except ValueError:
                continue
            if not isinstance(arguments, dict):
                continue
            calls[call_id] = (stamp, name, arguments, data.get("turn"))
            order.append(call_id)
        elif kind == "tool/result" and row.get("surfaceOp") == "append":
            message = data.get("message")
            if not isinstance(message, dict):
                continue
            call_id = message.get("toolCallId")
            if not isinstance(call_id, str) or call_id not in calls:
                continue
            meta = data.get("meta")
            path_value = meta.get("path") if isinstance(meta, dict) else None
            text = ""
            if calls[call_id][1] == "bash":
                content = message.get("content")
                text = "".join(piece.get("text", "") for piece in content
                               if isinstance(piece, dict) and piece.get("type") == "text"
                               and isinstance(piece.get("text"), str)) if isinstance(content, list) else ""
            exit_code = DSH_EXIT.search(text)
            success = (message.get("isError") is False
                       and (exit_code is None or exit_code[1] == "0")
                       and DSH_TERMINATED.search(text) is None)
            results[call_id] = (stamp, success, path_value, data.get("turn"))
        elif kind == "job/registered" and data.get("kind") == "bash":
            tool_call = data.get("toolCall")
            call_id = tool_call.get("callId") if isinstance(tool_call, dict) else None
            if isinstance(call_id, str):
                registered.add(call_id)
        elif kind == "job/settled" and data.get("kind") == "bash":
            tool_call = data.get("toolCall")
            call_id = tool_call.get("callId") if isinstance(tool_call, dict) else None
            if isinstance(call_id, str):
                settled[call_id] = data.get("status") == "completed" and data.get("detail") == "exit code: 0"
    if header is None:
        raise ValueError("missing DSH header")
    edits = []
    commands = []
    for call_id in order:
        call = calls.get(call_id)
        result = results.get(call_id)
        if call is None or result is None:
            continue
        start, name, arguments, turn_number = call
        end, success, path_value, result_turn = result
        if start is None or end is None or end < start or turn_number != result_turn:
            continue
        if name == "bash":
            success = success and settled.get(call_id, call_id not in registered)
            if success:
                commands.append((start, end, arguments.get("command")))
        elif success:
            key = "notebook_path" if name == "notebook_edit" else "file_path"
            arguments = dict(arguments)
            if isinstance(path_value, str) and path_value:
                arguments[key] = path_value
            edits.append((start, {"write": "Write", "edit": "Edit", "multi_edit": "MultiEdit",
                                  "notebook_edit": "NotebookEdit"}[name], arguments))
    return edits, commands, turn_start


def dsh_successful_edits(path, tail=None, turn=False, deadline=None):
    edits, _, start = dsh_calls(path, tail=tail, turn=turn, deadline=deadline)
    return ([(stamp, name, data) for stamp, name, data in edits
             if not turn or start is None or stamp >= start], start if turn else None)


def dsh_edited_paths(path, tail=None):
    edited = set()
    for _, name, data in dsh_successful_edits(path, tail=tail)[0]:
        value = data.get(EDIT_TOOLS[name])
        if isinstance(value, str) and Path(value).is_absolute():
            edited.add(Path(value).resolve())
    return edited


def dsh_transcript_evidence(path, spec_mtime, candidates):
    if Path(path).stat().st_mtime_ns <= spec_mtime:
        return False
    edits, commands, _ = dsh_calls(path)
    for stamp, name, data in edits:
        value = data.get(EDIT_TOOLS[name])
        if stamp > spec_mtime and candidate_path(value, candidates) is not None:
            return True
    return any(command_evidence(command, start, end, candidates)
               for start, end, command in commands)
