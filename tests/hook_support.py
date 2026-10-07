"""Shared black-box fixtures for the SessionStart and Stop hook tests."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SESSION_START = REPO / ".claude" / "hooks" / "session_start.py"
STOP_GUARD = REPO / ".claude" / "hooks" / "stop_guard.py"

class HookCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".scratch").mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def reset_root(self):
        self.temp.cleanup()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".scratch").mkdir()

    def run_hook(self, script, payload=None, *, cwd=None, raw=None):
        if raw is None:
            raw = json.dumps({} if payload is None else payload, ensure_ascii=False)
        result = subprocess.run(
            [sys.executable, str(script)],
            input=raw,
            text=True,
            capture_output=True,
            cwd=str(self.root if cwd is None else cwd),
            timeout=60,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return result.stdout

    def run_session(self, payload=None, *, cwd=None, raw=None):
        return self.run_hook(SESSION_START, payload, cwd=cwd, raw=raw)

    def run_stop(self, payload=None, *, cwd=None, raw=None):
        if payload is None and raw is None:
            payload = self.stop_payload()
        return self.run_hook(STOP_GUARD, payload, cwd=cwd, raw=raw)

    def make_task(self, name, status="in-progress", progress=None, scope=None):
        task = self.root / ".scratch" / name
        task.mkdir(parents=True, exist_ok=True)
        spec = task / "spec.md"
        lines = [f"Status: {status}", ""]
        if scope is not None:
            lines[1:1] = [f"Scope: {scope}"]
        if progress is not None:
            lines.append("## 进展")
            lines.extend(progress)
        spec.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return task, spec

    @staticmethod
    def set_mtime(path, ns):
        os.utime(path, ns=(ns, ns))

    def stop_fixture(self, *, status="in-progress"):
        task, spec = self.make_task("active", status)
        code = self.root / "src" / "changed.py"
        code.parent.mkdir()
        code.write_text("changed = True\n", encoding="utf-8")
        base = 1_900_000_000_000_000_000
        self.set_mtime(spec, base + 100)
        self.set_mtime(code, base + 300)
        return task, spec, code, base

    @staticmethod
    def stamp(ns, offset=0):
        zone = timezone(timedelta(hours=offset))
        whole, fraction = divmod(ns, 1_000_000_000)
        return datetime.fromtimestamp(whole, zone).strftime("%Y-%m-%dT%H:%M:%S") + (
            f".{fraction:09d}{'Z' if offset == 0 else f'{offset:+03d}:00'}"
        )

    def transcript(self, *rows, path=None, mtime=None):
        path = self.root / ".claude" / "history.jsonl" if path is None else path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(
            row if isinstance(row, str) else json.dumps(row, ensure_ascii=False)
            for row in rows
        ) + "\n", encoding="utf-8")
        self.set_mtime(path, 1_900_000_000_000_001_000 if mtime is None else mtime)
        return path

    def stop_payload(self, transcript=None, **extra):
        return {"cwd": str(self.root), "stop_hook_active": False,
                "transcript_path": str(transcript or self.root / ".claude" / "history.jsonl"), **extra}

    def claude_call(self, tool, data, start, end, *, call_id="call-1", error=False):
        return (
            {"type": "assistant", "timestamp": self.stamp(start), "cwd": str(self.root),
             "message": {"content": [{"type": "tool_use", "id": call_id,
                                       "name": tool, "input": data}]}},
            {"type": "user", "timestamp": self.stamp(end),
             "message": {"content": [{"type": "tool_result",
                                       "tool_use_id": call_id, "is_error": error,
                                       "content": "ok"}]}},
        )

    def named_edit(self, path=None, *, tool="Edit", field=None, end=None, error=False):
        _, spec, code, base = self.stop_fixture()
        path = code if path is None else path
        field = field or ("notebook_path" if tool == "NotebookEdit" else "file_path")
        rows = self.claude_call(tool, {field: str(path)}, base + 200,
                                base + 400 if end is None else end, error=error)
        return self.transcript(*rows), spec, code, base

    def assert_session_context(self, output, context):
        self.assertEqual(
            json.loads(output),
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context,
                }
            },
        )

    def assert_block(self, output, task_name):
        self.assertEqual(
            json.loads(output),
            {
                "decision": "block",
                "reason": (
                    f"[harness] Task {task_name} 本轮有代码改动但进展未更新:"
                    f"在 .scratch/{task_name}/spec.md 的 ## 进展 末尾追加一行"
                    "(done / next / 别再试)再停。"
                ),
            },
        )
