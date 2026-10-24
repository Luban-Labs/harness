"""SessionStart claim state and takeover notice with an isolated HOME."""

import json
import os
import subprocess
import sys
import time
from unittest.mock import patch

from hook_support import HookCase


class TakeoverBoardTest(HookCase):
    SESSION = "82e319f6-1111-2222-3333-444444444444"

    def setUp(self):
        super().setUp()
        bin_dir = self.home / "bin"
        bin_dir.mkdir()
        ps = bin_dir / "ps"
        # Claude Code records procStart in UTC; real ps prints local time unless TZ=UTC.
        ps.write_text("#!/bin/sh\nprintf x >> \"$HOME/ps-calls\"\n"
                      "if [ \"$TZ\" = UTC ]; then printf 'start marker\\n'; "
                      "else printf 'local marker\\n'; fi\n",
                      encoding="utf-8")
        ps.chmod(0o700)
        self.path_patch = patch.dict(os.environ, {"PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]})
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        super().tearDown()

    def task(self, claim=None, name="task", progress=""):
        path = self.root / ".scratch" / name
        path.mkdir()
        (path / "spec.md").write_text(
            "Status: in-progress\n" + (f"会话: {claim}\n" if claim else "")
            + "\n## 进展\n" + progress, encoding="utf-8")

    def context(self, session=None):
        output = self.run_session({"cwd": str(self.root), "session_id": session or self.SESSION})
        return json.loads(output)["hookSpecificOutput"]["additionalContext"] if output else ""

    def record(self, claim=None, hours=0, codex=False):
        claim = claim or self.SESSION
        if codex:
            path = self.home / ".codex/sessions/2026/10/24" / f"rollout-2026-10-24-{claim}.jsonl"
        else:
            path = self.home / ".claude/projects/project" / f"{claim}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
        stamp = time.time() - hours * 3600 - 2
        os.utime(path, (stamp, stamp))
        return path

    def registration(self, pid=None, proc_start=None, **extra):
        path = self.home / ".claude/sessions" / "entry.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "sessionId": self.SESSION, "pid": os.getpid() if pid is None else pid,
            "procStart": "start marker" if proc_start is None else proc_start, **extra,
        }), encoding="utf-8")

    def test_live_recent_and_stale(self):
        self.task(self.SESSION)
        self.registration()
        self.record(hours=2)
        self.assertIn("会话 82e319f6(在做)", self.context())
        self.record(hours=11)
        self.assertIn("会话 82e319f6(挂着 11 小时)", self.context())

    def test_exited_pid_and_reused_pid_are_broken(self):
        self.task(self.SESSION)
        self.record(hours=3)
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        child.wait()
        dead = child.pid
        self.registration(pid=dead)
        self.assertIn("会话 82e319f6(断了 3 小时)", self.context())
        self.registration(proc_start="wrong process start")
        self.assertIn("会话 82e319f6(断了 3 小时)", self.context())

    def test_claude_record_without_registration_and_prefix(self):
        self.task(self.SESSION[:8])
        self.record(hours=3)
        self.assertIn("会话 82e319f6(断了 3 小时)", self.context())
        self.registration()
        self.assertIn("会话 82e319f6(在做)", self.context())

    def test_codex_recent_and_old(self):
        self.task(self.SESSION)
        self.record(hours=2, codex=True)
        self.assertIn("会话 82e319f6(在做)", self.context())
        self.record(hours=12, codex=True)
        self.assertIn("会话 82e319f6(断了 12 小时)", self.context())

    def test_missing_record_has_no_label_and_bad_json_is_skipped(self):
        self.task(self.SESSION)
        self.assertIn("会话 82e319f6 ·", self.context())
        bad = self.home / ".claude/sessions/bad.json"
        bad.parent.mkdir(parents=True)
        bad.write_text("{", encoding="utf-8")
        self.registration()
        self.record(hours=2)
        self.assertIn("会话 82e319f6(在做)", self.context())

    def test_live_without_record_uses_updated_at_and_caches_ps(self):
        self.task(self.SESSION, name="first")
        self.task(self.SESSION[:8], name="second")
        self.registration(updatedAt=int((time.time() - 11 * 3600 - 2) * 1000))
        context = self.context()
        self.assertEqual(context.count("会话 82e319f6(挂着 11 小时)"), 2)
        self.assertEqual((self.home / "ps-calls").read_text(), "x")

    def test_ps_without_output_uses_process_presence(self):
        self.task(self.SESSION)
        self.registration()
        self.record(hours=2)
        ps = self.home / "bin/ps"
        ps.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        self.assertIn("会话 82e319f6(在做)", self.context())

    def test_missing_fields_fall_back_and_subhour_wording(self):
        self.task(self.SESSION)
        registry = self.home / ".claude/sessions/missing.json"
        registry.parent.mkdir(parents=True)
        registry.write_text(json.dumps({"sessionId": self.SESSION, "pid": os.getpid()}))
        self.record(hours=0)
        self.assertIn("会话 82e319f6(断了 不到 1 小时)", self.context())

    def test_codex_uses_newest_record(self):
        self.task(self.SESSION)
        self.record(hours=12, codex=True)
        newest = self.home / ".codex/sessions/other" / f"rollout-later-{self.SESSION}.jsonl"
        newest.parent.mkdir(parents=True)
        newest.write_text("{}\n")
        self.assertIn("会话 82e319f6(在做)", self.context())

    def test_takeover_notice_only_for_old_owner(self):
        self.task("newowner-1234", progress="- done: 接手自 82e319f6\n")
        context = self.context()
        self.assertEqual(context.splitlines()[1],
                         "[harness] 你认领过的 Task task 已被会话 newowner 接手:别再改它的 spec 与代码,有话用 ListAgents 发给新会话。")
        self.assertNotIn("你认领过", self.context("newowner-1234"))
        self.assertNotIn("你认领过", self.context("different-1234"))
        spec = self.root / ".scratch/task/spec.md"
        spec.write_text(spec.read_text().replace("newowner-1234", self.SESSION))
        self.assertNotIn("你认领过", self.context())

    def test_no_task_is_zero_output(self):
        self.record(hours=2)
        self.assertEqual(self.run_session({"cwd": str(self.root), "session_id": self.SESSION}), "")
