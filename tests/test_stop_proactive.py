"""Black-box tests for Stop's session-owned Task reminders."""

import json
import shlex

from hook_support import HookCase


class StopProactiveTest(HookCase):
    SESSION = "cb260c48-3465-481c-9e57-cea155732e77"

    def task(
        self,
        *,
        name="active",
        status="in-progress",
        session=None,
        checks=(),
        progress=(),
        scope=None,
        root=None,
    ):
        root = self.root if root is None else root
        folder = root / ".scratch" / name
        folder.mkdir(parents=True, exist_ok=True)
        header = [f"Status: {status}"]
        if scope is not None:
            header.append(f"Scope: {scope}")
        if session is not None:
            header.append(f"会话: {session}")
        lines = header + [
            "",
            "# Task",
            "",
            "## 验收",
            *checks,
            "",
            "## 进展",
            *progress,
        ]
        spec = folder / "spec.md"
        spec.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return spec

    def output(self, *, session=None, codex=False, cwd=None, **extra):
        payload = {
            "cwd": str(self.root if cwd is None else cwd),
            "stop_hook_active": False,
            **extra,
        }
        if session is not None:
            payload["session_id"] = session
        if codex:
            payload["turn_id"] = "turn-1"
        return self.run_stop(payload)

    def linked_root(self):
        linked = self.root / "linked"
        (linked / ".scratch").mkdir(parents=True)
        gitdir = self.root / ".git" / "worktrees" / "linked"
        gitdir.mkdir(parents=True)
        (linked / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
        (gitdir / "gitdir").write_text(str(linked / ".git") + "\n", encoding="utf-8")
        (gitdir / "commondir").write_text("../..\n", encoding="utf-8")
        return linked

    def test_forged_worktree_link_does_not_claim_foreign_task(self):
        linked = self.root / "linked"
        (linked / ".scratch").mkdir(parents=True)
        foreign = self.task(
            name="foreign", session=self.SESSION, checks=["- [ ] [我] test"],
            progress=["- 10-22 09:00 done: x | next: 我: work"],
        )
        gitdir = self.root / ".git" / "worktrees" / "missing"
        (linked / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
        self.assertTrue(foreign.is_file())
        self.assertEqual(self.output(session=self.SESSION, cwd=linked), "")

    def assert_reminder(self, output, message, *, codex=False):
        expected = (
            {"decision": "block", "reason": message}
            if codex
            else {
                "hookSpecificOutput": {
                    "hookEventName": "Stop",
                    "additionalContext": message,
                }
            }
        )
        self.assertEqual(json.loads(output), expected)

    def test_priority_done_and_missing_checks(self):
        done = self.task(
            status="done",
            session=self.SESSION,
            checks=["- [ ] [我] test"],
            progress=["- 10-22 09:00 done: x | next: 我: work"],
        )
        self.assert_reminder(
            self.output(session=self.SESSION),
            "[harness] Task active 已是 done 但还在 .scratch/:在主工作树执行 mkdir -p .scratch/archive && mv .scratch/active .scratch/archive/active。",
        )
        done.write_text(
            "Status: in-progress\n会话: "
            + self.SESSION
            + "\n\n## 验收\n\n## 进展\n- 10-22 09:00 done: x | next: 我: work\n",
            encoding="utf-8",
        )
        self.assert_reminder(
            self.output(session=self.SESSION),
            "[harness] Task active 的「## 验收」还没有带执行者的勾选框:改写成 - [ ] [我] … / - [ ] [你] …;[我] 是你当场能演示并自验的,[你] 是只有 owner 能做或要 owner 看的。",
        )

    def test_archive_command_quotes_each_task_path(self):
        name = "bad ; touch escaped ' quote"
        self.task(name=name, status="done", session=self.SESSION)
        message = json.loads(self.output(session=self.SESSION))["hookSpecificOutput"]["additionalContext"]
        command = message.split("在主工作树执行 ", 1)[1].removesuffix("。")
        self.assertEqual(
            command,
            f"mkdir -p .scratch/archive && mv {shlex.quote('.scratch/' + name)} "
            f"{shlex.quote('.scratch/archive/' + name)}",
        )

    def test_checked_self_items_take_priority_over_next_and_owner_items(self):
        self.task(
            session=self.SESSION[:8],
            checks=["- [X] [我] test", "- [ ] [你] approve"],
            progress=["- 10-22 09:00 done: x | next: 我: work"],
        )
        self.assert_reminder(
            self.output(session=self.SESSION),
            "[harness] Task active 的 [我] 验收项已全部勾上:现在做收件两问,改 Status: done 并归档;没勾的 [你] 项留在 spec 里,看板会继续列给 owner。",
        )
        self.assertEqual(self.output(session="different-session"), "")
        self.assertEqual(self.output(session=self.SESSION[:7]), "")

    def test_next_self_blocks_unless_background_work_exists(self):
        self.task(
            session=self.SESSION,
            checks=["- [ ] [我] test"],
            progress=[
                "- 10-22 09:00 done: x | next: 我: finish implementation | 别再试: x"
            ],
        )
        message = (
            "[harness] Task active 的 next 是你自己的事(finish implementation):接着做,"
            "做完勾上对应的验收项;[我] 项全勾就直接收件两问、改 done、归档,不要把核验或关闭写成「你:」。"
            "做不了就先追加一行进展,把 next 改成「你: <owner 要做的具体动作>」或"
            "「等: <在等什么>(回看: <几点、由谁、怎么看>)」再停;owner 让停或本轮在问别的事时写「等: owner 下一步安排(回看: owner 下次开口)」。"
        )
        self.assert_reminder(self.output(session=self.SESSION), message)
        self.assert_reminder(
            self.output(session=self.SESSION, codex=True), message, codex=True
        )
        for field in ("background_tasks", "session_crons"):
            with self.subTest(field=field):
                self.assertEqual(
                    self.output(session=self.SESSION, **{field: ["running"]}), ""
                )
                self.assert_reminder(
                    self.output(session=self.SESSION, **{field: []}), message
                )
        spec = self.root / ".scratch" / "active" / "spec.md"
        spec.write_text(
            spec.read_text(encoding="utf-8").replace(
                "next: 我: finish implementation",
                "next: 等: owner 下一步安排(回看: owner 下次开口)",
            ),
            encoding="utf-8",
        )
        self.assertEqual(self.output(session=self.SESSION), "")

    def test_wait_requires_review_only_without_background_work(self):
        spec = self.task(
            session=self.SESSION,
            checks=["- [ ] [我] test"],
            progress=["- 10-22 09:00 done: x | next: 等: CI"],
        )
        message = "[harness] Task active 在等外部但没写怎么回看:挂后台命令或 Monitor 等结果,或在 next 里补「回看: <几点、由谁、怎么看>」再停。"
        self.assert_reminder(self.output(session=self.SESSION), message)
        self.assertEqual(
            self.output(session=self.SESSION, session_crons=["cron-1"]), ""
        )
        spec.write_text(
            spec.read_text(encoding="utf-8").replace(
                "等: CI", "等: CI(回看：明天我检查)"
            ),
            encoding="utf-8",
        )
        self.assertEqual(self.output(session=self.SESSION), "")

    def test_missing_progress_or_ball_blocks_but_owner_ball_does_not(self):
        spec = self.task(session=self.SESSION, checks=["- [ ] [我] test"])
        message = "[harness] Task active 的进展末行没写球在谁手里:追加一行进展,next 以「我:」「等:」「你:」开头。"
        self.assert_reminder(self.output(session=self.SESSION), message)
        spec.write_text(
            spec.read_text(encoding="utf-8")
            + "- 10-22 09:00 done: x | next: undecided\n",
            encoding="utf-8",
        )
        self.assert_reminder(self.output(session=self.SESSION), message)
        spec.write_text(
            spec.read_text(encoding="utf-8").replace(
                "next: undecided", "next: 你: approve"
            ),
            encoding="utf-8",
        )
        self.assertEqual(self.output(session=self.SESSION), "")

    def test_multiple_owned_tasks_combine_one_first_match_each(self):
        self.task(
            name="alpha",
            session=self.SESSION,
            checks=["- [ ] [我] test"],
            progress=["- 10-22 09:00 done: x | next: 我: A"],
        )
        self.task(
            name="beta",
            session=self.SESSION,
            checks=["- [ ] [我] test"],
            progress=["- 10-22 09:00 done: x | next: 你: B"],
        )
        self.task(
            name="gamma",
            session=self.SESSION,
            status="done",
            checks=["- [ ] [我] test"],
        )
        output = self.output(session=self.SESSION)
        context = json.loads(output)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Task alpha 的 next", context)
        self.assertIn("Task gamma 已是 done", context)
        self.assertNotIn("Task beta", context)
        self.assertEqual(context.count("[harness]"), 2)

    def test_stop_hook_active_and_unowned_task_are_silent(self):
        self.task(
            session=self.SESSION,
            checks=["- [ ] [我] test"],
            progress=["- 10-22 09:00 done: x | next: 我: work"],
        )
        self.assertEqual(self.output(session=self.SESSION, stop_hook_active=True), "")
        self.assertEqual(self.output(session="another-id"), "")

    def test_codex_complete_input_shape_fullwidth_colons_and_60_characters(self):
        next_text = "验" * 61
        spec = self.task(
            session=self.SESSION,
            checks=["- [ ] [我] test"],
            progress=[f"- 10-22 09:00 done: x | next：我：{next_text}"],
        )
        spec.write_text(
            spec.read_text(encoding="utf-8")
            .replace("Status:", "Status：")
            .replace("会话:", "会话："),
            encoding="utf-8",
        )
        payload = {
            "cwd": str(self.root),
            "hook_event_name": "Stop",
            "last_assistant_message": "FIRST_STOP",
            "model": "gpt-6-luna",
            "permission_mode": "default",
            "session_id": self.SESSION,
            "stop_hook_active": False,
            "transcript_path": None,
            "turn_id": "turn-1",
        }
        output = json.loads(self.run_stop(payload))
        self.assertEqual(set(output), {"decision", "reason"})
        self.assertEqual(output["decision"], "block")
        self.assertIn(f"自己的事({next_text[:60]}):接着做,", output["reason"])
        self.assertNotIn(next_text, output["reason"])
        payload["stop_hook_active"] = True
        self.assertEqual(self.run_stop(payload), "")

    def test_claim_requires_equality_or_at_least_eight_prefix_characters(self):
        for claim, session, expected in (
            (self.SESSION[:7], self.SESSION, False),
            (self.SESSION[:8], self.SESSION, True),
            (self.SESSION[:7], self.SESSION[:7], True),
            (self.SESSION + "-extra", self.SESSION, False),
        ):
            with self.subTest(claim=claim, session=session):
                self.task(
                    session=claim,
                    checks=["- [ ] [我] test"],
                    progress=["- 10-22 09:00 done: x | next: 我: work"],
                )
                self.assertEqual(bool(self.output(session=session)), expected)

    def test_only_owner_checks_or_incomplete_self_checks_do_not_close(self):
        for checks in (
            ["- [ ] [你] approve"],
            ["- [x] [我] first", "- [ ] [我] second", "- [ ] [你] approve"],
        ):
            with self.subTest(checks=checks):
                self.task(
                    session=self.SESSION,
                    checks=checks,
                    progress=["- 10-22 09:00 done: x | next: 你: approve"],
                )
                self.assertEqual(self.output(session=self.SESSION), "")

    def test_bad_spec_does_not_release_an_owned_proactive_reminder(self):
        self.task(
            session=self.SESSION,
            checks=["- [ ] [我] test"],
            progress=["- 10-22 09:00 done: x | next: 我: work"],
        )
        broken = self.root / ".scratch" / "broken"
        broken.mkdir()
        (broken / "spec.md").write_bytes(b"Status: in-progress\n\xff")
        self.assertIn(
            "Task active 的 next 是你自己的事",
            json.loads(self.output(session=self.SESSION))["hookSpecificOutput"]["additionalContext"],
        )

    def test_owned_one_uses_legacy_fallback_and_owned_many_skip_it(self):
        self.task(
            session=self.SESSION,
            checks=["- [ ] [我] test"],
            progress=["- 10-22 09:00 done: x | next: 你: approve"],
        )
        spec = self.root / ".scratch" / "active" / "spec.md"
        code = self.root / "changed.py"
        code.write_text("x", encoding="utf-8")
        base = 1_900_000_000_000_000_000
        self.set_mtime(spec, base + 100)
        self.set_mtime(code, base + 300)
        transcript = self.transcript(
            *self.claude_call("Edit", {"file_path": str(code)}, base + 200, base + 400)
        )
        old = (
            "[harness] Task active 本轮有代码改动但进展未更新:"
            "在 .scratch/active/spec.md 的 ## 进展 末尾追加一行(done / next / 别再试)再停。"
        )
        self.assert_reminder(
            self.output(session=self.SESSION, transcript_path=str(transcript)), old
        )
        self.task(
            name="second",
            session=self.SESSION,
            checks=["- [ ] [我] test"],
            progress=["- 10-22 09:00 done: x | next: 你: approve"],
        )
        self.assertEqual(
            self.output(session=self.SESSION, transcript_path=str(transcript)), ""
        )

    def test_unowned_fallback_keeps_unique_scope_and_skips_bad_spec(self):
        _, spec = self.make_task("alpha", scope="src/")
        self.make_task("beta")
        src = self.root / "src"
        src.mkdir()
        code = src / "changed.py"
        code.write_text("x", encoding="utf-8")
        base = 1_900_000_000_000_000_000
        self.set_mtime(spec, base + 100)
        self.set_mtime(code, base + 300)
        transcript = self.transcript(
            *self.claude_call("Edit", {"file_path": str(code)}, base + 200, base + 400)
        )
        output = self.output(
            session="unowned", cwd=src, transcript_path=str(transcript)
        )
        self.assertIn(
            "Task alpha 本轮有代码改动",
            json.loads(output)["hookSpecificOutput"]["additionalContext"],
        )
        broken = self.root / ".scratch" / "broken"
        broken.mkdir()
        (broken / "spec.md").write_bytes(b"Status: in-progress\n\xff")
        self.assertIn(
            "Task alpha 本轮有代码改动",
            json.loads(self.output(session="unowned", cwd=src, transcript_path=str(transcript)))["hookSpecificOutput"]["additionalContext"],
        )

    def test_unowned_fallback_skips_task_claimed_by_another_session(self):
        spec = self.task(
            session="other-session-id",
            checks=["- [ ] [我] test"],
            progress=["- 10-22 09:00 done: x | next: 你: approve"],
        )
        code = self.root / "changed.py"
        code.write_text("x", encoding="utf-8")
        base = 1_900_000_000_000_000_000
        self.set_mtime(spec, base + 100)
        self.set_mtime(code, base + 300)
        transcript = self.transcript(
            *self.claude_call("Edit", {"file_path": str(code)}, base + 200, base + 400)
        )
        payload = {"session": "no-task-session", "transcript_path": str(transcript)}
        self.assertEqual(self.output(**payload), "")
        self.task(checks=["- [ ] [我] test"], progress=["- 10-22 09:00 done: x | next: 你: approve"])
        self.set_mtime(spec, base + 100)
        self.assertIn(
            "Task active 本轮有代码改动",
            json.loads(self.output(**payload))["hookSpecificOutput"]["additionalContext"],
        )

    def test_unowned_fallback_with_claimed_and_legacy_tasks_stays_silent(self):
        claimed = self.task(name="a-claimed", session="other-session-id", checks=["- [ ] [我] test"])
        legacy = self.task(name="b-legacy", checks=["- [ ] [我] test"])
        code = self.root / "changed.py"
        code.write_text("x", encoding="utf-8")
        base = 1_900_000_000_000_000_000
        self.set_mtime(claimed, base + 100)
        self.set_mtime(legacy, base + 100)
        self.set_mtime(code, base + 300)
        transcript = self.transcript(
            *self.claude_call("Edit", {"file_path": str(code)}, base + 200, base + 400)
        )
        self.assertEqual(
            self.output(session="no-task-session", transcript_path=str(transcript)), ""
        )

    def test_worktree_reads_main_task_but_fallback_scans_linked_tree(self):
        main = self.root
        linked = self.linked_root()
        spec = self.task(
            session=self.SESSION,
            checks=["- [ ] [我] test"],
            progress=["- 10-22 09:00 done: x | next: 你: approve"],
        )
        code = linked / "changed.py"
        code.write_text("x", encoding="utf-8")
        base = 1_900_000_000_000_000_000
        self.set_mtime(spec, base + 100)
        self.set_mtime(code, base + 300)
        transcript = self.transcript(
            *self.claude_call("Edit", {"file_path": str(code)}, base + 200, base + 400)
        )
        self.assertIn(
            "Task active 本轮有代码改动",
            json.loads(
                self.output(
                    session=self.SESSION, cwd=linked, transcript_path=str(transcript)
                )
            )["hookSpecificOutput"]["additionalContext"],
        )

    def test_unclaimed_linked_worktree_ignores_main_task_without_local_active_task(
        self,
    ):
        linked = self.linked_root()
        main_spec = self.task(name="main-only", checks=["- [ ] [我] test"])
        code = linked / "changed.py"
        code.write_text("x", encoding="utf-8")
        base = 1_900_000_000_000_000_000
        self.set_mtime(main_spec, base + 100)
        self.set_mtime(code, base + 300)
        transcript = self.transcript(
            *self.claude_call("Edit", {"file_path": str(code)}, base + 200, base + 400)
        )
        self.assertEqual(
            self.output(
                session="unclaimed", cwd=linked, transcript_path=str(transcript)
            ),
            "",
        )

    def test_unclaimed_linked_worktree_uses_local_task_name_and_spec_mtime(self):
        linked = self.linked_root()
        main_spec = self.task(name="main-only", checks=["- [ ] [我] test"])
        local_spec = self.task(
            name="local-task", checks=["- [ ] [我] test"], root=linked
        )
        code = linked / "changed.py"
        code.write_text("x", encoding="utf-8")
        base = 1_900_000_000_000_000_000
        self.set_mtime(main_spec, base + 100)
        self.set_mtime(local_spec, base + 350)
        self.set_mtime(code, base + 300)
        transcript = self.transcript(
            *self.claude_call("Edit", {"file_path": str(code)}, base + 200, base + 400)
        )
        payload = {
            "session": "unclaimed",
            "cwd": linked,
            "transcript_path": str(transcript),
        }
        self.assertEqual(self.output(**payload), "")
        self.set_mtime(local_spec, base + 100)
        output = self.output(**payload)
        self.assertIn(
            "Task local-task 本轮有代码改动",
            json.loads(output)["hookSpecificOutput"]["additionalContext"],
        )

    def test_unclaimed_local_fallback_survives_bad_main_spec(self):
        linked = self.linked_root()
        local_spec = self.task(name="local", root=linked, checks=["- [ ] [我] test"])
        code = linked / "changed.py"
        code.write_text("x", encoding="utf-8")
        base = 1_900_000_000_000_000_000
        self.set_mtime(local_spec, base + 100)
        self.set_mtime(code, base + 300)
        transcript = self.transcript(
            *self.claude_call("Edit", {"file_path": str(code)}, base + 200, base + 400)
        )
        broken = self.root / ".scratch" / "broken"
        broken.mkdir()
        spec = broken / "spec.md"
        for kind in ("header", "scope", "encoding", "symlink", "directory"):
            with self.subTest(kind=kind):
                if spec.is_dir():
                    spec.rmdir()
                elif spec.exists() or spec.is_symlink():
                    spec.unlink()
                if kind == "header":
                    spec.write_text("Status: in-progress\nbad header\n", encoding="utf-8")
                elif kind == "scope":
                    spec.write_text("Status: in-progress\nScope: ../escape\n", encoding="utf-8")
                elif kind == "encoding":
                    spec.write_bytes(b"Status: in-progress\n\xff")
                elif kind == "symlink":
                    spec.symlink_to(local_spec)
                else:
                    spec.mkdir()
                output = self.output(session="unclaimed", cwd=linked, transcript_path=str(transcript))
                self.assertIn(
                    "Task local 本轮有代码改动",
                    json.loads(output)["hookSpecificOutput"]["additionalContext"],
                )


if __name__ == "__main__":
    import unittest

    unittest.main()
