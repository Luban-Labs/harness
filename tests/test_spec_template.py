"""Black-box coverage for spec creation and the seventh Stop reminder."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys

from hook_support import HookCase, REPO, SESSION_START


SESSION = "cb260c48-3465-481c-9e57-cea155732e77"
TEMPLATE = REPO / ".agents/skills/interview-me/templates/spec.md"
PROGRESS = "- 10-22 09:00 done: 已完成 | next: 你: 确认"


class SpecTemplateTest(HookCase):
    def template(self, content=None):
        path = self.root / ".agents/skills/interview-me/templates/spec.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(TEMPLATE.read_text(encoding="utf-8") if content is None else content,
                        encoding="utf-8")
        return path

    def command(self, *args, cwd=None):
        return subprocess.run(
            [sys.executable, str(SESSION_START), *args], cwd=cwd or self.root,
            text=True, capture_output=True, timeout=60,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )

    def create(self, name="task", kind="功能"):
        self.template()
        result = self.command("--new-task", name, "--kind", kind)
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        spec = self.root / ".scratch" / name / "spec.md"
        self.assertTrue(result.stdout.startswith(str(spec.resolve())), result.stdout)
        self.assertIn("按模板逐节填写;必填节没内容写「无」", result.stdout)
        return spec

    def ready_spec(self, kind="功能", session=SESSION):
        spec = self.create(kind=kind)
        text = spec.read_text(encoding="utf-8")
        text = re.sub(r"<[^<>]+>", "已填", text)
        text = text.replace("Status: ready-for-agent", "Status: in-progress\n会话: " + session)
        text = text.replace("## 进展\n", "## 进展\n" + PROGRESS + "\n")
        spec.write_text(text, encoding="utf-8")
        return spec

    def message(self, **extra):
        payload = {"cwd": str(self.root), "session_id": SESSION,
                   "stop_hook_active": False, **extra}
        output = self.run_stop(payload)
        if not output:
            return ""
        value = json.loads(output)
        return value.get("reason", value.get("hookSpecificOutput", {}).get("additionalContext"))

    def test_generates_both_kinds_and_board_reads_ready_specs(self):
        for kind, present, absent in (
            ("功能", ("解法", "实现决策", "测试决策", "未知", "用户故事"), ()),
            ("记录", (), ("解法", "实现决策", "测试决策", "未知", "用户故事")),
        ):
            with self.subTest(kind=kind):
                spec = self.create(kind, kind)
                text = spec.read_text(encoding="utf-8")
                self.assertTrue(text.startswith(f"Status: ready-for-agent\n类型: {kind}\n"))
                self.assertIn(f"# {kind}\n", text)
                self.assertNotIn("<!-- 记录可省 -->", text)
                self.assertNotIn("\n\n\n", text)
                self.assertIn("<一句话>", text)
                for title in present:
                    self.assertIn(f"## {title}\n", text)
                for title in absent:
                    self.assertNotIn(f"## {title}\n", text)
        board = self.command("--board")
        self.assertIn("待开工 Task: 功能, 记录;", board.stdout)
        from importlib.util import module_from_spec, spec_from_file_location
        module_spec = spec_from_file_location("session_start_for_test", SESSION_START)
        module = module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        for kind in ("功能", "记录"):
            task = module.read_task(self.root / ".scratch" / kind / "spec.md", self.root)
            self.assertEqual((task["status"], task["checks"]), ("ready-for-agent", []))

    def test_rejects_invalid_names_kinds_shapes_and_existing_directory(self):
        self.template()
        for name in ("", "a/b", "a\\b", "a\nb", "a\rb", ".hidden", "archive"):
            with self.subTest(name=name):
                result = self.command("--new-task", name, "--kind", "功能")
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertEqual(len(result.stderr.splitlines()), 1)
                self.assertNotIn("Traceback", result.stderr)
        for args in (("--new-task", "x", "--kind", "其它"),
                     ("--new-task", "x"), ("--kind", "功能"),
                     ("--new-task", "x", "--kind", "功能", "--cwd")):
            with self.subTest(args=args):
                result = self.command(*args)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertEqual(len(result.stderr.splitlines()), 1)
        folder = self.root / ".scratch" / "taken"
        folder.mkdir()
        result = self.command("--new-task", "taken", "--kind", "功能")
        self.assertEqual(result.returncode, 1)
        self.assertFalse((folder / "spec.md").exists())

    def test_rejects_missing_or_unfenced_template_without_creating_directory(self):
        for content in (None, "# No Markdown code block\n", "```md\nStatus: ready-for-agent\n"):
            with self.subTest(content=content):
                path = self.root / ".agents/skills/interview-me/templates/spec.md"
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    self.template(content)
                result = self.command("--new-task", "missing", "--kind", "记录")
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertFalse((self.root / ".scratch" / "missing").exists())

    def test_cwd_uses_main_worktree_and_board_skips_placeholder_owner_check(self):
        self.template()
        linked = self.root / "linked"
        (linked / ".scratch").mkdir(parents=True)
        gitdir = self.root / ".git/worktrees/linked"
        gitdir.mkdir(parents=True)
        (linked / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
        (gitdir / "gitdir").write_text(str(linked / ".git") + "\n", encoding="utf-8")
        (gitdir / "commondir").write_text("../..\n", encoding="utf-8")
        result = self.command("--new-task", "linked-task", "--kind", "功能",
                              "--cwd", str(linked))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / ".scratch/linked-task/spec.md").exists())
        self.assertFalse((linked / ".scratch/linked-task").exists())
        spec = self.root / ".scratch/linked-task/spec.md"
        text = spec.read_text(encoding="utf-8").replace(
            "Status: ready-for-agent", "Status: in-progress\n会话: " + SESSION)
        spec.write_text(text, encoding="utf-8")
        output = self.run_session({"cwd": str(linked), "session_id": SESSION})
        context = json.loads(output)["hookSpecificOutput"]["additionalContext"]
        self.assertIn(f"[harness] 本会话 ID: {SESSION};开工或接手 Task 时写进它 spec 头部「会话:」行;建 Task 用 python3 .claude/hooks/session_start.py --new-task <名> --kind 功能|记录", context)
        self.assertNotIn("等你的事", context)

    def test_seventh_rule_collects_each_template_problem(self):
        changes = (
            ("missing", lambda text: text.replace("## 解法\n\n已填\n\n", ""), "缺必填节: 解法"),
            ("extra", lambda text: text + "\n## 额外\n已填\n", "骨架以外的节: 额外"),
            ("placeholder", lambda text: text.replace("## 问题\n\n已填", "## 问题\n\n<用户视角下用户面对的问题;bug 写现象与复现>"), "还留着骨架占位行"),
            ("length", lambda text: text.replace(PROGRESS, PROGRESS + "长" * 180), "进展最后一行超过 200 字"),
            ("count", lambda text: text + "\n".join([PROGRESS] * 30) + "\n", "进展超过 30 行"),
            ("scope", lambda text: text.replace("会话: " + SESSION, "会话: " + SESSION + "\nScope: .scratch/task"), "Scope 落在 .scratch 内"),
            ("goal", lambda text: re.sub(r"^目标:.*$", "", text, flags=re.M), "缺必填节: 目标"),
        )
        for label, change, expected in changes:
            with self.subTest(label=label):
                self.reset_root()
                spec = self.ready_spec()
                spec.write_text(change(spec.read_text(encoding="utf-8")), encoding="utf-8")
                self.assertIn(expected, self.message())

    def test_record_and_missing_type_require_only_record_sections(self):
        for kind in ("记录", ""):
            with self.subTest(kind=kind):
                self.reset_root()
                spec = self.ready_spec(kind="记录")
                text = spec.read_text(encoding="utf-8")
                if not kind:
                    text = text.replace("类型: 记录\n", "")
                spec.write_text(text, encoding="utf-8")
                self.assertEqual(self.message(), "")
                spec.write_text(text.replace("## 问题\n\n已填\n\n", ""), encoding="utf-8")
                self.assertIn("缺必填节: 问题", self.message())

    def test_priority_one_to_six_omits_seventh_rule(self):
        variants = (
            lambda text: text.replace("Status: in-progress", "Status: done"),
            lambda text: re.sub(r"^- \[[ x]\] \[[我你]\].*\n", "", text, flags=re.M),
            lambda text: text.replace("- [ ] [我]", "- [x] [我]"),
            lambda text: text.replace("next: 你: 确认", "next: 我: 继续"),
            lambda text: text.replace("next: 你: 确认", "next: 等: CI"),
            lambda text: text.replace(PROGRESS, "未写球"),
        )
        for index, mutate in enumerate(variants, 1):
            with self.subTest(rule=index):
                self.reset_root()
                spec = self.ready_spec()
                text = spec.read_text(encoding="utf-8")
                text = mutate(text.replace("## 解法\n\n已填\n\n", ""))
                spec.write_text(text, encoding="utf-8")
                message = self.message()
                self.assertTrue(message)
                self.assertNotIn("spec 不合模板", message)

    def test_unclaimed_written_spec_and_foreign_claim_boundaries(self):
        spec = self.ready_spec(session="")
        text = spec.read_text(encoding="utf-8").replace("会话: \n", "")
        spec.write_text(text.replace("## 解法\n\n已填\n\n", ""), encoding="utf-8")
        base = 1_900_000_000_000_000_000
        self.set_mtime(spec, base + 300)
        transcript = self.transcript(*self.claude_call(
            "Edit", {"file_path": str(spec)}, base + 200, base + 400))
        self.assertIn("缺必填节: 解法", self.message(transcript_path=str(transcript)))
        self.assertEqual(self.message(), "")
        other_transcript = self.transcript(*self.claude_call(
            "Edit", {"file_path": str(spec)}, base + 200, base + 400),
            path=self.root / ".claude/other-session.jsonl")
        self.assertEqual(self.message(transcript_path=str(self.root / ".claude/current-session.jsonl")), "")
        self.assertTrue(other_transcript.is_file())
        spec.write_text(spec.read_text(encoding="utf-8").replace(
            "Status: in-progress", "Status: in-progress\n会话: other-session"), encoding="utf-8")
        self.assertEqual(self.message(transcript_path=str(transcript)), "")

    def test_missing_template_checks_only_progress_and_scope(self):
        spec = self.ready_spec()
        self.root.joinpath(".agents/skills/interview-me/templates/spec.md").unlink()
        text = spec.read_text(encoding="utf-8")
        text = text.replace("## 解法\n\n已填\n\n", "") + "\n## 额外\n"
        spec.write_text(text, encoding="utf-8")
        self.assertEqual(self.message(), "")
        spec.write_text(text.replace(PROGRESS, PROGRESS + "长" * 180).replace(
            "会话: " + SESSION, "会话: " + SESSION + "\nScope: .scratch/task"),
            encoding="utf-8")
        message = self.message()
        self.assertIn("进展最后一行超过 200 字", message)
        self.assertIn("Scope 落在 .scratch 内", message)
        self.assertNotIn("缺必填节", message)
        self.assertNotIn("骨架以外", message)
        spec.write_text(text.replace(PROGRESS, "\n".join([PROGRESS] * 31)), encoding="utf-8")
        self.assertIn("进展超过 30 行", self.message())

    def test_multiple_problems_in_one_reminder_and_progress_boundaries(self):
        spec = self.ready_spec()
        text = spec.read_text(encoding="utf-8").replace("## 解法\n\n已填\n\n", "")
        text += "\n## 额外\n"
        spec.write_text(text, encoding="utf-8")
        message = self.message()
        self.assertIn("缺必填节: 解法;骨架以外的节: 额外", message)
        text = text.replace("## 额外\n", "## 解法\n")
        length = len(PROGRESS)
        spec.write_text(text.replace(PROGRESS, PROGRESS + "字" * (200 - length)), encoding="utf-8")
        self.assertEqual(self.message(), "")
        spec.write_text(text.replace(PROGRESS, PROGRESS + "字" * (201 - length)), encoding="utf-8")
        self.assertIn("进展最后一行超过 200 字", self.message())

    def test_codex_shape_combines_multiple_tasks_and_active_stop_is_silent(self):
        first = self.ready_spec()
        second = self.create("second")
        text = first.read_text(encoding="utf-8").replace("## 解法\n\n已填\n\n", "")
        first.write_text(text, encoding="utf-8")
        second.write_text(text.replace("# task", "# second"), encoding="utf-8")
        payload = {"cwd": str(self.root), "session_id": SESSION, "turn_id": "t1",
                   "stop_hook_active": False}
        output = json.loads(self.run_stop(payload))
        self.assertEqual(output["decision"], "block")
        self.assertIn("Task task 的 spec 不合模板", output["reason"])
        self.assertIn("Task second 的 spec 不合模板", output["reason"])
        self.assertEqual(self.run_stop({**payload, "stop_hook_active": True}), "")

    def test_unclaimed_spec_without_type_is_not_checked_even_if_edited(self):
        spec = self.ready_spec(session="")
        text = spec.read_text(encoding="utf-8").replace("会话: \n", "").replace("类型: 功能\n", "")
        spec.write_text(text.replace("## 解法\n\n已填\n\n", "") + "\n## 额外\n", encoding="utf-8")
        base = 1_900_000_000_000_000_000
        self.set_mtime(spec, base + 300)
        transcript = self.transcript(*self.claude_call(
            "Edit", {"file_path": str(spec)}, base + 200, base + 400))
        self.assertEqual(self.message(transcript_path=str(transcript)), "")

    def test_fullwidth_type_header_selects_record_sections(self):
        spec = self.ready_spec(kind="记录")
        text = spec.read_text(encoding="utf-8").replace("类型: 记录", "类型：记录")
        spec.write_text(text, encoding="utf-8")
        self.assertEqual(self.message(), "")

    def test_new_task_refuses_symlinked_scratch(self):
        self.template()
        scratch = self.root / ".scratch"
        target = self.root / "elsewhere"
        target.mkdir()
        for path in sorted(scratch.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        scratch.rmdir()
        scratch.symlink_to(target)
        result = self.command("--new-task", "linked", "--kind", "记录")
        self.assertEqual(result.returncode, 1)
        self.assertFalse((target / "linked").exists())

    def test_real_check_wrapped_in_tags_still_counts(self):
        spec = self.ready_spec()
        text = spec.read_text(encoding="utf-8").replace(
            "- [ ] [我] 已填",
            "- [x] [我] 已填\n- [ ] [我] <button>提交</button> 点击后应出现 <dialog>成功</dialog>",
        )
        spec.write_text(text, encoding="utf-8")
        self.assertNotIn("已全部勾上", self.message())

    def test_only_edit_tools_on_the_exact_path_attribute_an_unclaimed_spec(self):
        first = self.create("first")
        second = self.create("second")
        for spec in (first, second):
            text = re.sub(r"<[^<>]+>", "已填", spec.read_text(encoding="utf-8"))
            spec.write_text(text.replace("## 解法\n\n已填\n\n", ""), encoding="utf-8")
        base = 1_900_000_000_000_000_000
        self.set_mtime(first, base + 300)
        self.set_mtime(second, base + 300)
        reading = self.transcript(*self.claude_call(
            "Bash", {"command": f"cat {first}"}, base + 200, base + 400))
        self.assertEqual(self.message(transcript_path=str(reading)), "")
        editing = self.transcript(*self.claude_call(
            "Edit", {"file_path": str(second)}, base + 200, base + 400))
        message = self.message(transcript_path=str(editing))
        self.assertIn("Task second 的 spec 不合模板", message)
        self.assertNotIn("Task first", message)
