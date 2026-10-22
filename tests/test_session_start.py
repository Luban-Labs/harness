"""SessionStart board and the parser shared with Stop."""

import json
import os
import runpy
import subprocess
import sys
import unittest
from datetime import datetime, timedelta

from hook_support import SESSION_START, HookCase


sys.dont_write_bytecode = True
hook = runpy.run_path(str(SESSION_START))


class SessionStartTest(HookCase):
    def context(self, payload=None):
        output = self.run_session(payload)
        return json.loads(output)["hookSpecificOutput"]["additionalContext"] if output else ""

    def board(self, cwd=None):
        result = subprocess.run(
            [sys.executable, str(SESSION_START), "--board", "--cwd", str(cwd or self.root)],
            input="", text=True, capture_output=True, cwd=self.root, timeout=60,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        return result.stdout

    def spec(self, name, content, *, archive=False):
        base = self.root / ".scratch" / ("archive" if archive else "") / name
        base.mkdir(parents=True, exist_ok=True)
        path = base / "spec.md"
        path.write_text(content, encoding="utf-8")
        return path

    def test_zero_bytes_without_any_listed_task(self):
        self.assertEqual(self.run_session({"cwd": str(self.root), "session_id": "abcdefgh"}), "")
        self.assertEqual(self.board(), "")
        self.spec("archived", "Status: done\n\n## 验收\n- [x] [你] 已验收\n", archive=True)
        self.assertEqual(self.run_session({"cwd": str(self.root), "session_id": "abcdefgh"}), "")
        self.assertEqual(self.board(), "")
        (self.root / ".scratch").rename(self.root / "elsewhere")
        self.assertEqual(self.run_session({"cwd": str(self.root)}), "")

    def test_claims_owner_active_ready_and_board_mode(self):
        progress = "- 10-22 12:00 done: 已查 | next: 你: 批准方案 | 别再试: 旧接口"
        self.spec("active", "Status: in-progress\nTickets: A\n会话：abcdefgh\nScope: src/\n\n"
                  f"## 验收\n- [ ] [我] 测试\n\n## 进展\n{progress}\n")
        self.spec("ready", "Status: ready-for-agent\n")
        self.spec("closed", "Status: done\n\n## 验收\n- [ ] [你] 看效果\n", archive=True)
        context = self.context({"cwd": str(self.root), "session_id": "abcdefgh-1234"})
        self.assertTrue(context.startswith("[harness] 本会话 ID: abcdefgh-1234;"))
        self.assertIn(f"本会话认领: active(.scratch/active/spec.md) 最近进展: {progress}", context)
        self.assertIn("等你的事 2 条:", context)
        self.assertIn("- active: 批准方案(", context)
        self.assertIn("- closed(已归档): 看效果", context)
        self.assertIn("进行中 Task 1 个:", context)
        self.assertIn("· 会话 abcdefgh ·", context)
        self.assertIn("· 你: 批准方案", context)
        self.assertIn("待开工 Task: ready;", context)
        plain = self.board()
        self.assertNotIn("本会话 ID", plain)
        self.assertNotIn("本会话认领", plain)
        self.assertEqual(plain.rstrip("\n"), "\n".join(context.splitlines()[2:]))

    def test_done_unarchived_is_listed_and_bad_spec_is_skipped(self):
        self.spec("done", "Status: done\n\n## 进展\n- 10-22 10:00 done: 完成 | next: 我: 归档\n")
        self.spec("bad", "Status: in-progress\nScope: ../escape\n")
        self.spec("bad-header", "Status: in-progress\nnot a header\n")
        self.spec("bad-file", "Status: in-progress\n", archive=False).unlink()
        (self.root / ".scratch" / "bad-file" / "spec.md").mkdir()
        context = self.context({"cwd": str(self.root)})
        self.assertIn("进行中 Task 1 个:", context)
        self.assertIn("- done · 无人认领 ·", context)
        self.assertIn("· 待归档: 归档", context)
        self.assertNotIn("bad-header", context)

    def test_checked_self_items_show_pending_closure_before_next_ball(self):
        progress = "## 进展\n- 10-22 10:00 done: tested | next: 你: approve\n"
        checks = "## 验收\n- [x] [我] test\n- [ ] [你] approve\n\n"
        self.spec("close", f"Status: in-progress\n\n{checks}{progress}")
        self.spec("owner-only", "Status: in-progress\n\n## 验收\n- [ ] [你] approve\n\n" + progress)
        self.spec("partial", "Status: in-progress\n\n## 验收\n- [x] [我] first\n- [ ] [我] second\n\n" + progress)
        self.spec("done", f"Status: done\n\n{checks}{progress}")
        for output in (self.board(), self.context({"cwd": str(self.root)})):
            self.assertIn("- close · 无人认领 ·", output)
            self.assertIn("· 待结案: approve", next(line for line in output.splitlines() if line.startswith("- close ·")))
            self.assertIn("· 待归档: approve", next(line for line in output.splitlines() if line.startswith("- done ·")))
            for name in ("owner-only", "partial"):
                self.assertIn("· 你: approve", next(line for line in output.splitlines() if line.startswith(f"- {name} ·")))

    def test_caps_and_order(self):
        for index in range(12):
            self.spec(f"t{index:02d}", "Status: in-progress\n\n## 进展\n"
                      "- 10-22 10:00 done: ok | next: 你: 审核\n")
        for index in range(7):
            self.spec(f"r{index:02d}", "Status: ready-for-agent\n")
        board = self.board()
        self.assertIn("等你的事 12 条:", board)
        self.assertIn("- 等 12 条", board)
        self.assertIn("进行中 Task 12 个:", board)
        self.assertIn("- 等 12 个", board)
        self.assertIn("待开工 Task: r00, r01, r02, r03, r04 等 7 个;", board)
        self.assertNotIn("- t11:", board)
        self.assertNotIn("- t11 ·", board)

    def test_active_next_truncates_at_80_characters_in_hook_and_cli(self):
        for length in (79, 80, 81):
            with self.subTest(length=length):
                next_text = "验" * length
                progress = f"- 10-22 10:00 done: ok | next: 我: {next_text} | 别再试: 无"
                self.spec("active", "Status: in-progress\n会话: abcdefgh\n\n"
                          f"## 进展\n{progress}\n")
                context = self.context({"cwd": str(self.root), "session_id": "abcdefgh-1234"})
                self.assertIn(f"最近进展: {progress}", context)
                for output in (context, self.board()):
                    row = next(line for line in output.splitlines() if line.startswith("- active ·"))
                    self.assertEqual(row.split(" · 我: ", 1)[1], next_text[:80])

    def test_archive_scan_cap_and_pending_owner_only(self):
        for index in range(1002):
            self.spec(f"a{index:04d}", "Status: done\n\n## 验收\n- [ ] [你] 确认\n", archive=True)
        board = self.board()
        self.assertIn("等你的事 1000 条:", board)
        self.assertNotIn("进行中 Task", board)

    def test_main_worktree_and_local_fallback(self):
        main = self.root / "main"
        linked = self.root / "linked"
        (main / ".git" / "worktrees" / "linked").mkdir(parents=True)
        (main / ".scratch" / "main-task").mkdir(parents=True)
        (main / ".scratch" / "main-task" / "spec.md").write_text("Status: ready-for-agent\n", encoding="utf-8")
        (linked / ".scratch" / "local-task").mkdir(parents=True)
        (linked / ".scratch" / "local-task" / "spec.md").write_text("Status: ready-for-agent\n", encoding="utf-8")
        (linked / ".git").write_text(f"gitdir: {main / '.git' / 'worktrees' / 'linked'}\n", encoding="utf-8")
        (main / ".git" / "worktrees" / "linked" / "gitdir").write_text(str(linked / ".git") + "\n", encoding="utf-8")
        (main / ".git" / "worktrees" / "linked" / "commondir").write_text("../..\n", encoding="utf-8")
        nested = linked / "src" / "nested"
        nested.mkdir(parents=True)
        scan, task = hook["project_roots"](nested)
        self.assertEqual((scan, task), (linked.resolve(), main.resolve()))
        self.assertIn("main-task", self.board(nested))
        self.assertNotIn("local-task", self.board(nested))
        (linked / ".scratch").rename(linked / "real-scratch")
        (linked / ".scratch").symlink_to(linked / "real-scratch", target_is_directory=True)
        self.assertEqual(self.board(nested), "")
        (linked / ".scratch").unlink()
        (linked / "real-scratch").rename(linked / ".scratch")
        (main / ".scratch").rename(main / "moved")
        self.assertIn("local-task", self.board(nested))

    def test_forged_worktree_link_stays_on_local_task(self):
        main = self.root / "other"
        linked = self.root / "linked"
        (main / ".git" / "worktrees").mkdir(parents=True)
        (main / ".scratch" / "foreign").mkdir(parents=True)
        (main / ".scratch" / "foreign" / "spec.md").write_text("Status: ready-for-agent\n", encoding="utf-8")
        (linked / ".scratch" / "local").mkdir(parents=True)
        (linked / ".scratch" / "local" / "spec.md").write_text("Status: ready-for-agent\n", encoding="utf-8")
        gitdir = main / ".git" / "worktrees" / "linked"
        (linked / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
        for metadata in ("missing", "wrong-gitdir", "wrong-commondir"):
            with self.subTest(metadata=metadata):
                if gitdir.exists():
                    for item in gitdir.iterdir():
                        item.unlink()
                else:
                    gitdir.mkdir()
                if metadata != "missing":
                    (gitdir / "gitdir").write_text(
                        str((linked if metadata == "wrong-commondir" else main) / ".git") + "\n",
                        encoding="utf-8",
                    )
                if metadata == "wrong-commondir":
                    (gitdir / "commondir").write_text(str(linked) + "\n", encoding="utf-8")
                if metadata == "missing":
                    gitdir.rmdir()
                self.assertEqual(hook["project_roots"](linked), (linked.resolve(), linked.resolve()))
                self.assertIn("local", self.board(linked))
                self.assertNotIn("foreign", self.board(linked))

    def test_parser_contract_and_session_matching(self):
        spec = self.spec("one", "Status：in-progress\nTickets: GH-1\nScope：src/\n会话: abcdefgh\nOther: fine\n\n"
                         "## 验收 extra\n- [x] [我] 自测\n- [ ] [你] 批准\n"
                         "## 进展\n- 10-20 12:00 done: 旧 | next: 我: 旧\n"
                         "- 10-22 12:00 done: 新 | next：等：CI (回看：明天)\n")
        task = hook["read_task"](spec, self.root)
        self.assertEqual(task["name"], "one")
        self.assertEqual(task["status"], "in-progress")
        self.assertEqual(task["session"], "abcdefgh")
        self.assertEqual(task["scope_value"], "src/")
        self.assertEqual(task["scope"], (self.root / "src").resolve())
        self.assertEqual(task["checks"], [(True, "我", "自测"), (False, "你", "批准")])
        self.assertEqual((task["ball"], task["next"]), ("等", "CI (回看：明天)"))
        self.assertEqual(task["spec"], spec)
        self.assertIsInstance(task["mtime_ns"], int)
        self.assertTrue(hook["session_matches"]("abcdefgh", "abcdefgh-1234"))
        self.assertFalse(hook["session_matches"]("abcdefg", "abcdefg-1234"))
        self.assertFalse(hook["session_matches"]("abcdefgh-2", "abcdefgh-1234"))

    def test_bad_header_and_scope_are_individual_errors(self):
        for text in ("Status: ready-for-agent\nno colon\n", "Status: invalid\n",
                     "Status: in-progress\nScope: ../other\n",
                     "Status: in-progress\nScope: /absolute\n",
                     "Status: in-progress\nScope: src//bad\n"):
            with self.subTest(text=text):
                spec = self.spec("bad", text)
                with self.assertRaises(ValueError):
                    hook["read_task"](spec, self.root)
        self.spec("good", "Status: ready-for-agent\n")
        self.assertIn("good", self.board())
        self.assertNotIn("bad", self.board())

    def test_age_progress_date_and_mtime_fallback(self):
        now = datetime(2026, 1, 1, 0, 10)
        task = {"progress": "- 12-31 23:50 done: x | next: 你: y", "mtime_ns": 0}
        self.assertEqual(hook["age"](task, now), "20 分钟")
        task["progress"] = "- 02-30 12:00 done: x | next: 你: y"
        task["mtime_ns"] = int((now - timedelta(hours=3)).timestamp() * 1_000_000_000)
        self.assertEqual(hook["age"](task, now), "3 小时")
        task["progress"] = "- 12-30 00:00 done: x | next: 你: y"
        self.assertEqual(hook["age"](task, now), "2 天")
        leap = {"progress": "- 02-29 12:00 done: x | next: 你: y", "mtime_ns": 0}
        self.assertEqual(hook["age"](leap, datetime(2025, 3, 1, 12, 0)), "366 天")

    def test_fail_open_payload_and_symlink_root(self):
        self.spec("ready", "Status: ready-for-agent\n")
        for raw in ("", "{", "null", "[]", "1", '"text"'):
            with self.subTest(raw=raw):
                self.assertEqual(self.run_session(raw=raw), "")
        for payload in ({"cwd": 3}, {"cwd": []}, {"cwd": None}, {"session_id": 3}):
            self.assertEqual(self.run_session(payload), "")
        scratch = self.root / ".scratch"
        scratch.rename(self.root / "real-scratch")
        scratch.symlink_to(self.root / "real-scratch", target_is_directory=True)
        self.assertEqual(self.run_session({"cwd": str(self.root)}), "")
        self.assertEqual(self.board(), "")

    def test_session_marker_is_untouched(self):
        self.spec("active", "Status: in-progress\n")
        marker = self.root / ".scratch" / ".session"
        marker.touch()
        os.utime(marker, ns=(1_000_000_000, 1_000_000_000))
        for source in ("startup", "clear", "compact", "resume", None):
            payload = {"cwd": str(self.root), "source": source}
            self.assertIn("进行中 Task 1 个", self.context(payload))
            self.assertEqual(marker.stat().st_mtime_ns, 1_000_000_000)


if __name__ == "__main__":
    unittest.main()
