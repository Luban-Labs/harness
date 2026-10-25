#!/usr/bin/env python3
"""Dynamic Claude command-hook adapter for the installed DSH bridge.

Only stdin and stdout are protocol surfaces. Failures are silent, non-blocking.
Session paths and parentage are established here; consumers do not search again.
"""
import contextlib
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time


EVENTS = {"SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse",
          "Stop", "SubagentStart", "SubagentStop"}
TOOLS = {"bash": "Bash", "read": "Read", "write": "Write", "edit": "Edit",
         "glob": "Glob", "grep": "Grep", "subagent": "Agent", "subagent_fork": "Agent",
         "workflow": "Workflow", "todo_write": "TodoWrite", "web_search": "WebSearch",
         "web_fetch": "WebFetch"}
LOG_NAME = "session.v4.jsonl.zstd"
MAX_LOG = 64 * 1024 * 1024
MAX_JSON = 4 * 1024 * 1024
OUTPUT_LIMIT = 64000


@lru_cache(maxsize=2)
def hook_module(name):
    """Load the repository's shared judgments without cache writes or main()."""
    path = Path(__file__).resolve().parents[1] / ".claude/hooks" / (name + ".py")
    spec = importlib.util.spec_from_file_location("_harness_" + name, path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


class DispatchDeadline(BaseException):
    """Bypass per-source error handlers so the overall dispatch deadline wins."""


class DispatchBudget:
    def __enter__(self):
        self.started = time.monotonic()
        self.running = []
        self.cancelled = False
        self.previous_handler = signal.getsignal(signal.SIGALRM)
        self.previous_terminate = signal.getsignal(signal.SIGTERM)
        self.previous_timer = signal.getitimer(signal.ITIMER_REAL)
        def expired(_signum, _frame):
            raise DispatchDeadline()
        def terminate(_signum, _frame):
            self.cancelled = True
            for process in tuple(self.running):
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
            raise DispatchDeadline()
        signal.signal(signal.SIGALRM, expired)
        signal.signal(signal.SIGTERM, terminate)
        signal.setitimer(signal.ITIMER_REAL, 0.8)
        return self

    @contextlib.contextmanager
    def child_execution(self):
        remaining = signal.setitimer(signal.ITIMER_REAL, 0)
        try:
            yield
        finally:
            if remaining[0] > 0:
                signal.setitimer(signal.ITIMER_REAL, *remaining)

    def __exit__(self, *_error):
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, self.previous_handler)
        signal.signal(signal.SIGTERM, self.previous_terminate)
        remaining, interval = self.previous_timer
        if remaining:
            signal.setitimer(signal.ITIMER_REAL,
                             max(0.000001, remaining - (time.monotonic() - self.started)), interval)


def read_json(path):
    try:
        with open(path, encoding="utf-8") as stream:
            raw = stream.read(MAX_JSON + 1)
        value = json.loads(raw) if len(raw) <= MAX_JSON else None
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def git_roots(path):
    """Nearest worktree root and backlink-verified canonical repository root."""
    path = Path(path).resolve()
    for root in (path, *path.parents):
        marker = root / ".git"
        if marker.is_dir():
            return root, root
        if not marker.is_file():
            continue
        try:
            main = hook_module("session_start").main_worktree(root)
            if main is not None:
                return root, main
        except Exception:
            pass
        return root, root
    return None, None


def project_context(created_cwd, home=None):
    """CC ordinary-start settings roots, hook projectRoot and strict trust keys.

    DSH supplies no --projectConfigRoot or CC explicit-worktree lifecycle. Its
    persisted creation cwd is the only supported initial projectRoot evidence.
    """
    cwd = Path(created_cwd).resolve()
    home = Path.home() if home is None else Path(home)
    worktree, canonical = git_roots(cwd)
    trust_keys = [str(canonical)] if canonical else []
    for parent in (cwd, *cwd.parents):
        if str(parent) not in trust_keys:
            trust_keys.append(str(parent))
        if parent == worktree:
            break
    projects = read_json(home / ".claude.json").get("projects", {})
    trusted = isinstance(projects, dict) and any(
        isinstance(projects.get(key), dict)
        and projects[key].get("hasTrustDialogAccepted") is True for key in trust_keys)
    local = cwd
    if canonical is not None and canonical != cwd:
        try:
            uid = os.geteuid()
            entries = [canonical / ".git", canonical / ".claude"]
            if (canonical.stat().st_uid == uid and all(p.lstat().st_uid == uid
                    for p in entries if p.exists() or p.is_symlink())):
                local = canonical
        except (OSError, AttributeError):
            pass
    return {"project_dir": cwd, "settings_dir": cwd, "local_settings_dir": local,
            "trusted": bool(trusted), "trust_keys": trust_keys}


def trusted_project(path, home=None):
    return project_context(path, home)["trusted"]


def read_header(path):
    from compression import zstd  # Python < 3.14 deliberately degrades silently.
    with zstd.open(path, "rb") as stream:
        line = stream.readline(65537)
    if len(line) > 65536 or not line.endswith(b"\n"):
        return None
    header = json.loads(line)
    if (not isinstance(header, dict) or header.get("type") != "session"
            or type(header.get("version")) is not int or header["version"] != 4
            or header.get("id") != path.parent.name
            or not isinstance(header.get("cwd"), str)
            or not Path(header["cwd"]).is_absolute()
            or (header.get("parentSession") is not None
                and (not isinstance(header["parentSession"], str) or not header["parentSession"]))):
        return None
    if "parentSession" not in header:
        if not hook_module("session_start").DSH_SESSION.fullmatch(header["id"]):
            return None
        header["parentSession"] = None
    return header


def session_metadata(home, session_id, deadline, include_index=False):
    """Locate exact IDs, reject duplicate paths, and resolve descendant chains."""
    if (not isinstance(session_id, str) or not session_id or len(session_id) > 200
            or not re.fullmatch(r"[A-Za-z0-9_-]+", session_id)):
        return None, []
    base = home / ".dsh" / "sessions"
    if not base.is_dir() or base.is_symlink():
        return None, []
    current = []
    buckets = []
    for bucket in base.iterdir():
        if time.monotonic() > deadline:
            return None, []
        if bucket.is_dir() and not bucket.is_symlink():
            buckets.append(bucket)
            candidate = bucket / session_id / LOG_NAME
            if candidate.is_file() and not candidate.is_symlink() and not candidate.parent.is_symlink():
                current.append(candidate)
    if len(current) != 1:
        return None, []
    header = read_header(current[0])
    if header is None:
        return None, []
    metadata = {"session_id": session_id, "path": str(current[0]),
                "mtime": current[0].stat().st_mtime, "parent_session_id": header["parentSession"],
                "cwd": header["cwd"]}
    records = [metadata]
    if include_index:
        seen = {session_id: metadata}
        duplicates = set()
        for bucket in buckets:
            for child in bucket.iterdir():
                if time.monotonic() > deadline:
                    # A partial index cannot establish prefix uniqueness or ancestry.
                    return metadata, []
                path = child / LOG_NAME
                if path == current[0] or child.is_symlink() or not path.is_file() or path.is_symlink():
                    continue
                try:
                    other = read_header(path)
                    if other is None:
                        continue
                    sid = other["id"]
                    if sid in seen:
                        duplicates.add(sid)
                        continue
                    seen[sid] = {"session_id": sid, "path": str(path), "mtime": path.stat().st_mtime,
                                 "parent_session_id": other["parentSession"], "cwd": other["cwd"]}
                except Exception:
                    continue
        records = [row for key, row in seen.items() if key not in duplicates]
    return metadata, records


def current_turn(path, deadline):
    """A complete bounded v4 read; an unfinished/oversized read proves no turn."""
    from compression import zstd
    boundary_judgment = hook_module("stop_evidence").turn_boundary
    used, latest = 0, None
    with zstd.open(path, "rb") as stream:
        while True:
            if time.monotonic() > deadline:
                return None
            line = stream.readline(1024 * 1024 + 1)
            if not line:
                return latest
            used += len(line)
            if used > MAX_LOG or len(line) > 1024 * 1024 or not line.endswith(b"\n"):
                return None
            row = json.loads(line)
            if not isinstance(row, dict):
                return None
            boundary = boundary_judgment(row)
            if boundary is None:
                return None
            if boundary:
                latest = [row["seq"], row["data"]["turn"]]


def selected_matcher(pattern, subject, event):
    if event in {"Stop", "UserPromptSubmit"} or pattern in (None, "", "*"):
        return True
    if not isinstance(pattern, str):
        return False
    if re.fullmatch(r"[A-Za-z0-9_|, ]+", pattern):
        return subject in re.split(r"[|, ]+", pattern)
    try:
        return re.search(pattern, subject) is not None
    except re.error:
        return False


def plugin_configs(home, enabled, project_dir, deadline):
    installed = read_json(home / ".claude/plugins/installed_plugins.json").get("plugins", {})
    if not isinstance(installed, dict):
        return []
    configs = []
    _, canonical = git_roots(project_dir)
    for name, flag in enabled.items():
        if time.monotonic() > deadline:
            break
        if flag is not True:
            continue
        entries = installed.get(name, [])
        if not isinstance(entries, list):
            continue
        root = None
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("installPath"), str):
                continue
            project = entry.get("projectPath")
            accepted = entry.get("scope") in {"user", "managed"}
            if isinstance(project, str):
                accepted = accepted or Path(project).resolve() == project_dir
                if not accepted and canonical is not None:
                    accepted = git_roots(project)[1] == canonical
            candidate = Path(entry["installPath"])
            if accepted and candidate.is_absolute() and candidate.is_dir():
                root = candidate.resolve()
                break
        if root is None:
            continue
        manifest = read_json(root / ".claude-plugin/plugin.json")
        declared = manifest.get("hooks", [])
        declared = declared if isinstance(declared, list) else [declared]
        paths = set()
        for item in ["hooks/hooks.json", *declared]:
            if isinstance(item, dict):
                configs.append((item, root))
            elif isinstance(item, str):
                path = (root / item.replace("${CLAUDE_PLUGIN_ROOT}", str(root))).resolve()
                try:
                    path.relative_to(root)
                except ValueError:
                    continue
                if path not in paths:
                    paths.add(path)
                    configs.append((read_json(path), root))
    return configs


def collect_hooks(home, project, payload, deadline):
    sources = [(read_json(home / ".claude/settings.json"), None)]
    if project["trusted"]:
        files = [project["settings_dir"] / ".claude/settings.json",
                 project["local_settings_dir"] / ".claude/settings.local.json",
                 project["settings_dir"] / ".claude/settings.local.json"]
        seen = set()
        for path in files:
            if path not in seen:
                seen.add(path)
                sources.append((read_json(path), None))
    enabled = {}
    for settings, _ in sources:
        values = settings.get("enabledPlugins", {})
        if isinstance(values, dict):
            enabled.update(values)
    sources.extend(plugin_configs(home, enabled, project["project_dir"], deadline))
    event = payload["hook_event_name"]
    subject = payload.get("tool_name", "") if event in {"PreToolUse", "PostToolUse"} else (
        payload.get("source", "") if event == "SessionStart" else payload.get("agent_type", ""))
    commands = []
    for settings, plugin_root in sources:
        if time.monotonic() > deadline:
            break
        mapping = settings.get("hooks", settings)
        groups = mapping.get(event, []) if isinstance(mapping, dict) else []
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict) or not selected_matcher(group.get("matcher"), subject, event):
                continue
            hooks = group.get("hooks", [])
            if not isinstance(hooks, list):
                continue
            for hook in hooks:
                if (isinstance(hook, dict) and hook.get("type", "command") == "command"
                        and isinstance(hook.get("command"), str)):
                    commands.append((hook, plugin_root))
    return commands


def run_command(hook, plugin_root, payload, project_dir, budget=None):
    timeout = hook.get("timeout", 600)
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or timeout <= 0):
        return None
    env = {**os.environ, "HARNESS_HOST": "dsh", "CLAUDE_PROJECT_DIR": str(project_dir)}
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    if plugin_root is not None:
        env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
    command = hook["command"]
    shell = "args" not in hook
    if not shell:
        args = hook["args"]
        if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
            return None
        command = [command, *args]
        for variable in ("CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT"):
            if variable in env:
                command = [part.replace("${" + variable + "}", env[variable]) for part in command]
    working = payload.get("cwd")
    working = Path(working) if isinstance(working, str) and Path(working).is_absolute() else project_dir
    if not working.is_dir():
        working = project_dir
    encoded = (json.dumps(payload, ensure_ascii=False) + "\n").encode()
    if budget is not None and budget.cancelled:
        return None
    proc = subprocess.Popen(command, shell=shell, **({"executable": "/bin/sh"} if shell else {}), cwd=working,
                            env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, start_new_session=True)
    if budget is not None:
        budget.running.append(proc)
        if budget.cancelled:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
    try:
        stdout, stderr = proc.communicate(encoded, timeout=timeout)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        return None
    finally:
        if budget is not None:
            budget.running.remove(proc)
    if proc.returncode not in (0, 2):
        return None
    return (proc.returncode, stdout[-OUTPUT_LIMIT:].decode("utf-8", "replace"),
            stderr[-OUTPUT_LIMIT:].decode("utf-8", "replace"))


def decode_output(code, stdout, stderr, event):
    if code == 2:
        return {"decision": "deny", "reason": stderr.strip()}
    stdout = stdout.strip()
    if not stdout:
        return None
    if not stdout.startswith("{"):
        return {"context": stdout} if event in {"SessionStart", "UserPromptSubmit"} else None
    try:
        parsed = json.loads(stdout)
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    result = {}
    if parsed.get("decision") in {"approve", "block"}:
        result["decision"] = "deny" if parsed["decision"] == "block" else "allow"
    if isinstance(parsed.get("reason"), str):
        result["reason"] = parsed["reason"]
    specific = parsed.get("hookSpecificOutput", {})
    if isinstance(specific, dict) and specific.get("hookEventName") == event:
        if specific.get("permissionDecision") in {"allow", "deny", "ask"}:
            result["decision"] = specific["permissionDecision"]
        if isinstance(specific.get("permissionDecisionReason"), str):
            result["reason"] = specific["permissionDecisionReason"]
        if isinstance(specific.get("additionalContext"), str):
            result["context"] = specific["additionalContext"]
    return result


@contextlib.contextmanager
def round_state(home, session_id):
    """Non-waiting per-session OS lock; corrupted or unavailable state is unknown."""
    import fcntl
    directory = home / ".dsh/harness-cc-hooks"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink():
        raise ValueError("unsafe state directory")
    key = hashlib.sha256(session_id.encode()).hexdigest()
    path = directory / (key + ".json")
    lock = os.open(directory / (key + ".lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if path.is_symlink():
            raise ValueError("unsafe state file")
        existed = path.exists()
        state = read_json(path)
        bound = (isinstance(state.get("turn"), list) and len(state["turn"]) == 2
                 and all(type(n) is int and n >= 0 for n in state["turn"]))
        pending = (state.get("turn") is None and state.get("prompt_pending") is True
                   and state.get("blocked") is True)
        if not ((bound or pending) and type(state.get("blocked")) is bool
                and type(state.get("prompt_pending", False)) is bool):
            if existed:
                raise ValueError("unknown round state")
            state = {}
        def save(value):
            descriptor, temporary = tempfile.mkstemp(prefix=key + ".", dir=directory)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    json.dump(value, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(temporary)
        yield state, save
    finally:
        os.close(lock)


def invoke_hooks(commands, payload, project_dir, can_block=False, blocked_callback=None, budget=None):
    if not commands:
        return None
    # CC starts every handler with the same input and gathers in config order.
    with budget.child_execution() if budget else contextlib.nullcontext():
        with ThreadPoolExecutor(max_workers=len(commands)) as pool:
            futures = [pool.submit(run_command, hook, plugin_root, payload, project_dir, budget)
                       for hook, plugin_root in commands]
            raw_outputs = []
            for future in futures:
                try:
                    raw_outputs.append(future.result())
                except Exception:
                    raw_outputs.append(None)
    outcomes = []
    event = payload["hook_event_name"]
    for raw in raw_outputs:
        if raw is None:
            continue
        result = decode_output(*raw, event)
        if not result:
            continue
        if event == "Stop" and result.get("decision") == "deny":
            if not can_block:
                result.pop("decision", None)
        outcomes.append(result)
    contexts = [row["context"] for row in outcomes if row.get("context")]
    rank = {"allow": 1, "ask": 2, "deny": 3}
    winning = max((rank.get(row.get("decision"), 0) for row in outcomes), default=0)
    if event == "Stop" and winning == 3:
        # Persist once before returning an event blocker. The next Stop sees true.
        blocked_callback()
    reason = "\n\n".join(row["reason"] for row in outcomes
                          if rank.get(row.get("decision"), 0) == winning and row.get("reason"))
    output = {}
    specific = {"hookEventName": event}
    if event in {"SessionStart", "UserPromptSubmit", "PostToolUse", "SubagentStart"} and contexts:
        specific["additionalContext"] = "\n\n".join(contexts)
    if event == "PreToolUse" and winning:
        specific["permissionDecision"] = {1: "allow", 2: "ask", 3: "deny"}[winning]
        if reason:
            specific["permissionDecisionReason"] = reason
    elif event in {"Stop", "UserPromptSubmit", "PostToolUse"} and winning == 3:
        output["decision"] = "block"
        if reason:
            output["reason"] = reason
    if len(specific) > 1:
        output["hookSpecificOutput"] = specific
    return output or None


def dispatch(payload, home=None):
    try:
        with DispatchBudget() as budget:
            return _dispatch(payload, home, budget)
    except DispatchDeadline:
        return None


def _dispatch(payload, home, budget):
    if not isinstance(payload, dict) or payload.get("hook_event_name") not in EVENTS:
        return None
    home = Path.home() if home is None else Path(home)
    event = payload["hook_event_name"]
    deadline = time.monotonic() + 0.8
    metadata, records = session_metadata(home, payload.get("session_id"), deadline,
                                         event in {"SessionStart", "Stop"})
    if metadata is None:
        return None
    project = project_context(metadata["cwd"], home)
    payload = {**payload, "transcript_path": "", "dsh_transcript_path": metadata["path"],
               "dsh_parent_session_id": metadata["parent_session_id"],
               "dsh_session_records": records, "dsh_child_transcript_paths": []}
    descendants = {metadata["session_id"]}
    while True:
        more = {row["session_id"] for row in records if row["parent_session_id"] in descendants}
        if more <= descendants:
            break
        descendants.update(more)
    payload["dsh_child_transcript_paths"] = [row["path"] for row in records
                                            if row["session_id"] in descendants
                                            and row["session_id"] != metadata["session_id"]]
    if event in {"PreToolUse", "PostToolUse"}:
        payload["tool_name"] = TOOLS.get(payload.get("tool_name"), payload.get("tool_name", ""))
        if payload["tool_name"] == "Grep" and isinstance(payload.get("tool_input"), dict):
            inputs = dict(payload["tool_input"])
            if "include" in inputs:
                inputs["glob"] = inputs.pop("include")
            payload["tool_input"] = inputs
        if isinstance(payload.get("tool_input"), dict):
            inputs = dict(payload["tool_input"])
            if payload["tool_name"] == "Bash" and "timeoutMs" in inputs:
                inputs["timeout"] = inputs["timeoutMs"]
            if payload["tool_name"] == "WebSearch":
                queries = inputs.get("queries")
                if isinstance(queries, list) and len(queries) == 1 and isinstance(queries[0], str):
                    inputs["query"] = queries[0]
            payload["tool_input"] = inputs
    commands = collect_hooks(home, project, payload, deadline)
    if event not in {"Stop", "UserPromptSubmit"}:
        return invoke_hooks(commands, payload, project["project_dir"], budget=budget)
    turn = current_turn(metadata["path"], deadline)
    if metadata["parent_session_id"] is not None:
        payload["stop_hook_active"] = True
        return invoke_hooks(commands, payload, project["project_dir"], budget=budget)
    with round_state(home, metadata["session_id"]) as (state, save):
        if event == "UserPromptSubmit":
            # pre-step can precede the persistence flush. Remember the prompt
            # without treating the old on-disk boundary as a new user turn.
            state = {**(state or {"turn": None, "blocked": True}), "prompt_pending": True}
            save(state)
        previous = state.get("turn")
        advanced = turn is not None and (previous is None or
                                        (turn[0] > previous[0] and turn[1] > previous[1]))
        if advanced and state.get("prompt_pending") is True:
            # The same pending prompt may first see its boundary at Stop.
            # A steer prompt with no new boundary never rearms this quota.
            state = {"turn": turn, "blocked": False, "prompt_pending": False}
            save(state)
        can_block = turn is not None and state.get("turn") == turn and state.get("blocked") is False
        if event == "Stop":
            payload["stop_hook_active"] = not can_block
        def mark_blocked():
            state["blocked"] = True
            save(state)
        return invoke_hooks(commands, payload, project["project_dir"], can_block, mark_blocked, budget)


def main():
    try:
        raw = sys.stdin.read(MAX_JSON + 1)
        if len(raw) > MAX_JSON:
            return
        result = dispatch(json.loads(raw))
        if result:
            print(json.dumps(result, ensure_ascii=False))
    except Exception:
        pass


if __name__ == "__main__":
    main()
