"""Synthetic v4 DSH frames for the Stop evidence contract."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from unittest import mock

try:
    from compression import zstd
except ImportError:
    zstd = None

from hook_support import HookCase, REPO, STOP_GUARD


SESSION = "session-11111111-2222-4333-8444-555555555555"
CHILD = "22222222-3333-4444-8555-666666666666"
BASE = 1_900_000_000_000_000_000


class DshEvidenceTest(HookCase):
    def setUp(self):
        with mock.patch.object(tempfile, "tempdir", str(REPO / ".tmp-tests")):
            super().setUp()

    def run_dsh(self, payload):
        result = subprocess.run(
            [sys.executable, str(STOP_GUARD)], input=json.dumps(payload), text=True,
            capture_output=True, cwd=self.root, timeout=60,
            env={**os.environ, "HOME": str(self.home), "HARNESS_HOST": "dsh",
                 "CLAUDE_PROJECT_DIR": str(self.root), "PYTHONDONTWRITEBYTECODE": "1",
                 "TMPDIR": str(REPO / ".tmp-tests")},
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        return result.stdout

    def payload(self, log, children=(), **extra):
        return {"cwd": str(self.root), "session_id": SESSION,
                "stop_hook_active": False, "transcript_path": "",
                "dsh_transcript_path": str(log),
                "dsh_child_transcript_paths": [str(p) for p in children],
                "dsh_parent_session_id": None, **extra}

    def log(self, rows, name="session.v4.jsonl.zstd"):
        if zstd is None:
            self.skipTest("compression.zstd needs Python 3.14")
        path = self.root / name
        path.write_bytes(b"".join(zstd.compress(json.dumps(row).encode() + b"\n") for row in rows))
        self.set_mtime(path, BASE + 800)
        return path

    def header(self, session=SESSION, parent=None, version=4):
        row = {"type": "session", "version": version, "id": session,
               "cwd": str(self.root)}
        if parent is not None:
            row["parentSession"] = parent
        return row

    @staticmethod
    def event(kind, time_ms, data, **extra):
        return {"type": kind, "time": time_ms, "data": data, **extra}

    def edit_rows(self, path, *, tool="write", call_id="c1", error=False,
                  operation="append", exit_text=None, turn=1):
        args = {"file_path": str(path), "content": "def synthetic_key(value):\n    return value\n"}
        if tool == "edit":
            args = {"file_path": str(path), "old_string": "x", "new_string": "y"}
        if tool == "bash":
            args = {"command": ": > " + path.name}
        return [
            self.event("tool/call", 1_900_000_000_200, {"callId": call_id,
                "turn": turn, "name": tool, "arguments": json.dumps(args)}),
            self.event("tool/result", 1_900_000_000_400, {"turn": turn,
                "meta": {"path": str(path)} if tool != "bash" else {},
                "message": {"toolCallId": call_id, "isError": error,
                            "content": [{"type": "text", "text": exit_text or "ok"}]}},
                surfaceOp=operation),
        ]

    def owned_task(self):
        task = self.root / ".scratch" / "active"
        task.mkdir(exist_ok=True)
        (task / "spec.md").write_text(
            "Status: in-progress\n会话: " + SESSION +
            "\n\n## 验收\n- [ ] [我] check\n\n## 进展\n"
            "- 10-25 09:00 done: x | next: 我: finish\n", encoding="utf-8")

    def test_owned_stop_blocks_with_host_marker_and_no_claude_transcript(self):
        self.owned_task()
        log = self.log([self.header()])
        out = json.loads(self.run_dsh(self.payload(log)))
        self.assertEqual(out["decision"], "block")
        self.assertIn("Task active", out["reason"])
        self.assertEqual(self.run_dsh(self.payload(log, stop_hook_active=True)), "")
        self.assertEqual(self.run_dsh(self.payload(log, dsh_parent_session_id=SESSION)), "")

    def test_write_evidence_without_final_assistant_and_frame_append(self):
        _, spec, code, _ = self.stop_fixture()
        self.set_mtime(spec, BASE + 100)
        self.set_mtime(code, BASE + 300)
        rows = [self.header(), self.event("turn/start", 1_900_000_000_100, {"turn": 1}, seq=1)]
        log = self.log(rows, "main.v4.jsonl.zstd")
        with log.open("ab") as stream:
            stream.write(b"".join(zstd.compress(json.dumps(row).encode() + b"\n")
                                  for row in self.edit_rows(code)))
        self.set_mtime(log, BASE + 800)
        out = json.loads(self.run_dsh(self.payload(log)))
        self.assertEqual(out["decision"], "block")
        self.assertIn("代码改动但进展未更新", out["reason"])

    def test_non_append_failed_and_nonzero_bash_are_not_evidence(self):
        _, _, code, _ = self.stop_fixture()
        self.set_mtime(code, BASE + 300_000_000)
        wrong_call_surface = self.edit_rows(code)
        wrong_call_surface[0]["surfaceOp"] = "append"
        unmatched = self.edit_rows(code)
        unmatched[1]["data"]["message"]["toolCallId"] = "unmatched"
        wrong_turn = self.edit_rows(code)
        wrong_turn[1]["data"]["turn"] = 2
        backwards = self.edit_rows(code)
        backwards[1]["time"] = 1_900_000_000_100
        for rows in (
            self.edit_rows(code, operation="replace"),
            wrong_call_surface,
            unmatched,
            wrong_turn,
            backwards,
            self.edit_rows(code)[:1],
            self.edit_rows(code, error=True),
            self.edit_rows(code, tool="bash", exit_text="[exit code: 7]"),
        ):
            with self.subTest(rows=rows[0]["data"]["name"]):
                log = self.log([self.header(), *rows])
                self.assertEqual(self.run_dsh(self.payload(log)), "")
        log = self.log([self.header(), *self.edit_rows(code, tool="bash",
                                  exit_text="[exit code: 0]")])
        self.assertIn("代码改动", json.loads(self.run_dsh(self.payload(log)))["reason"])

    def test_background_bash_requires_settled_success(self):
        _, _, code, _ = self.stop_fixture()
        self.set_mtime(code, BASE + 300_000_000)
        rows = self.edit_rows(code, tool="bash")
        registered = self.event("job/registered", 1_900_000_000_250,
                                {"kind": "bash", "toolCall": {"callId": "c1"}})
        failed = self.event("job/settled", 1_900_000_000_350,
                            {"kind": "bash", "toolCall": {"callId": "c1"},
                             "status": "failed", "detail": "exit code: 2"})
        ok = self.event("job/settled", 1_900_000_000_350,
                        {"kind": "bash", "toolCall": {"callId": "c1"},
                         "status": "completed", "detail": "exit code: 0"})
        self.assertEqual(self.run_dsh(self.payload(self.log([self.header(), rows[0],
                                                             registered, rows[1]]))), "")
        self.assertEqual(self.run_dsh(self.payload(self.log([self.header(), rows[0],
                                                             registered, failed, rows[1]]))), "")
        self.assertIn("代码改动", json.loads(self.run_dsh(self.payload(
            self.log([self.header(), rows[0], registered, ok, rows[1]]))))["reason"])

    def test_foreground_bash_killed_by_signal_is_not_success(self):
        _, _, code, _ = self.stop_fixture()
        self.set_mtime(code, BASE + 300_000_000)
        log = self.log([self.header(), *self.edit_rows(
            code, tool="bash", exit_text="[killed by signal: SIGTERM]")])
        self.assertEqual(self.run_dsh(self.payload(log)), "")

    def test_foreground_bash_terminal_failure_markers_are_not_success(self):
        _, _, code, _ = self.stop_fixture()
        self.set_mtime(code, BASE + 300_000_000)
        for marker in ("[timed out after 1000ms]", "[stopped: user request]",
                       "[sandbox: file access limited under workspace-write mode]"):
            with self.subTest(marker=marker):
                log = self.log([self.header(), *self.edit_rows(
                    code, tool="bash", exit_text=marker + "\n[exit code: 0]")])
                self.assertEqual(self.run_dsh(self.payload(log)), "")

    def test_only_descendant_header_contributes(self):
        _, _, code, _ = self.stop_fixture()
        main = self.log([self.header()], "parent.v4.jsonl.zstd")
        good = self.log([self.header(CHILD, SESSION), *self.edit_rows(code)],
                        "child.v4.jsonl.zstd")
        foreign = self.log([self.header("foreign", "other"), *self.edit_rows(code)],
                           "foreign.v4.jsonl.zstd")
        grandchild = self.log([self.header("grandchild", CHILD), *self.edit_rows(code)],
                              "grandchild.v4.jsonl.zstd")
        self.assertEqual(self.run_dsh(self.payload(main, (foreign,))), "")
        self.assertIn("代码改动", json.loads(self.run_dsh(self.payload(main, (foreign, good))))["reason"])
        parent_only = self.log([self.header(CHILD, SESSION)], "parent-child.v4.jsonl.zstd")
        self.assertIn("代码改动", json.loads(self.run_dsh(self.payload(
            main, (grandchild, parent_only))))["reason"])

    def test_main_header_must_match_payload_session(self):
        _, _, code, _ = self.stop_fixture()
        log = self.log([self.header("other"), *self.edit_rows(code)])
        self.assertEqual(self.run_dsh(self.payload(log)), "")

    def test_malformed_turn_start_fails_closed(self):
        _, _, code, _ = self.stop_fixture()
        starts = [
            self.event("turn/start", 1_900_000_000_100, {"turn": 1}),
            self.event("turn/start", 1_900_000_000_100, {"turn": True}, seq=1),
            self.event("turn/start", -1, {"turn": 1}, seq=1),
            self.event("turn/start", 1_900_000_000_100, None, seq=1),
        ]
        for index, start in enumerate(starts):
            with self.subTest(index=index):
                log = self.log([self.header(), start, *self.edit_rows(code)])
                self.assertEqual(self.run_dsh(self.payload(log)), "")

    def test_bad_version_and_corrupt_frames_drop_evidence_only(self):
        _, _, code, _ = self.stop_fixture()
        rows = [self.header(), *self.edit_rows(code)]
        bad_version = self.log([self.header(version=3), *self.edit_rows(code)])
        self.assertEqual(self.run_dsh(self.payload(bad_version)), "")
        damaged = self.log(rows, "damaged.v4.jsonl.zstd")
        with damaged.open("ab") as stream:
            stream.write(b"\x28\xb5\x2f\xfd\x20")
        self.assertEqual(self.run_dsh(self.payload(damaged)), "")
        self.owned_task()
        out = json.loads(self.run_dsh(self.payload(damaged)))
        self.assertIn("Task active", out["reason"])

    def test_unknown_identity_stays_silent(self):
        self.owned_task()
        log = self.log([self.header()])
        payload = self.payload(log)
        del payload["dsh_parent_session_id"]
        self.assertEqual(self.run_dsh(payload), "")
        self.assertEqual(self.run_dsh(self.payload(log, dsh_parent_session_id="")), "")

    def test_dsh_write_feeds_judgment_twin_reminder(self):
        if zstd is None:
            self.skipTest("compression.zstd needs Python 3.14")
        shutil.rmtree(self.root / ".git")
        env = {**os.environ, "HOME": str(self.home), "GIT_CONFIG_NOSYSTEM": "1",
               "TMPDIR": str(REPO / ".tmp-tests")}
        def git(*args):
            subprocess.run(["git", "-C", str(self.root), *args], check=True,
                           capture_output=True, env=env)
        git("init", "-q")
        (self.root / "section.py").write_text("def section_identity(value):\n    return value\n")
        git("add", "section.py")
        git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "base")
        content = "def section_matches(value):\n    return value\n"
        path = self.root / "new.py"
        path.write_text(content)
        rows = self.edit_rows(path)
        rows[0]["data"]["arguments"] = json.dumps({"file_path": str(path), "content": content})
        log = self.log([self.header(), self.event("turn/start", 1_900_000_000_100,
                                                 {"turn": 1}, seq=1), *rows])
        out = json.loads(self.run_dsh(self.payload(log)))
        self.assertIn("section_matches", out["reason"])
        self.assertIn("section_identity", out["reason"])

    def test_missing_compression_module_is_an_evidence_failure(self):
        spec = importlib.util.spec_from_file_location(
            "stop_evidence_dsh_probe", REPO / ".claude/hooks/stop_evidence.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with mock.patch.dict(sys.modules, {"compression": None}):
            with self.assertRaises(ImportError):
                next(module.dsh_records(self.root / "missing.v4.jsonl.zstd"))
