"""Black-box tests for judgments.py CLI commands and Stop table-shape reminders."""

import io
import json
import os
import shutil
import subprocess
import sys
import time
import unittest
from unittest import mock

from hook_support import REPO, HookCase


JUDGMENTS = REPO / ".claude" / "hooks" / "judgments.py"
TABLE = "docs/rules/core-judgments.md"
BASE = 1_900_000_000_000_000_000


def valid_section(name="同区", detail=False, impl="`src/a.py:same`",
                  defn="两个区名指同一区域。", exc="无", todo="无"):
    lines = [
        f"## {name}",
        f"- 定义:{defn}",
        f"- 唯一实现:{impl}",
        f"- 语义例外:{exc}",
        f"- 待收口:{todo}",
    ]
    if detail:
        lines.append(f"- 详情:`docs/judgments/{name}.md`")
    return "\n".join(lines)


class JudgmentsCliTest(HookCase):
    def cli(self, *args, cwd=None):
        return subprocess.run(
            [sys.executable, str(JUDGMENTS), *args],
            input="", text=True, capture_output=True,
            cwd=str(self.root if cwd is None else cwd),
            env={**os.environ, "HOME": str(self.home), "PYTHONDONTWRITEBYTECODE": "1"},
        )

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_help_ls_show_and_detail(self):
        help_res = self.cli("--help")
        self.assertEqual(help_res.returncode, 0, help_res.stderr)
        for token in ("ls", "show", "--detail", "check", "300", "120"):
            self.assertIn(token, help_res.stdout)

        self.write("docs/judgments/同区.md", "# 同区详情\n边界说明。\n")
        table = "# 核心判断\n\n说明。\n\n" + valid_section("同区", detail=True) + "\n\n" + valid_section("同场", impl="待定") + "\n"
        self.write(TABLE, table)

        ls_res = self.cli("ls")
        self.assertEqual((ls_res.returncode, ls_res.stderr), (0, ""))
        self.assertEqual(ls_res.stdout.splitlines(), [
            "同区: 两个区名指同一区域。",
            "同场: 两个区名指同一区域。",
        ])

        show_res = self.cli("show", "同区")
        self.assertEqual((show_res.returncode, show_res.stderr), (0, ""))
        self.assertEqual(show_res.stdout.strip(), valid_section("同区", detail=True))

        detail_res = self.cli("show", "同区", "--detail")
        self.assertEqual((detail_res.returncode, detail_res.stderr), (0, ""))
        self.assertIn(valid_section("同区", detail=True), detail_res.stdout)
        self.assertIn("# 同区详情", detail_res.stdout)

        check_res = self.cli("check")
        self.assertEqual((check_res.returncode, check_res.stdout, check_res.stderr), (0, "", ""))

        missing_res = self.cli("show", "不存在")
        self.assertNotEqual(missing_res.returncode, 0)

    def test_check_accepts_valid_variants_and_empty_table(self):
        self.write(TABLE, "# 核心判断\n\n空表说明。\n")
        res = self.cli("check")
        self.assertEqual((res.returncode, res.stdout), (0, ""))

        self.write("docs/judgments/多口.md", "边界内容。\n")
        multi = valid_section(
            "多口",
            detail=True,
            impl="`src/a.py:f`、`src/b.py:C.m`",
            exc="\n  - 甲例外\n  - 乙例外",
            todo="\n  - 待收口一",
        )
        self.write(TABLE, "# 核心判断\n\n" + multi + "\n")
        res = self.cli("check")
        self.assertEqual((res.returncode, res.stdout), (0, ""))

    def test_check_reports_every_shape_violation(self):
        self.write("docs/judgments/孤儿.md", "没有节指向我。\n")
        cases = [
            ("超长节", valid_section("超长节", defn="x" * 110, exc="y" * 110, todo="z" * 110), "超过 300 字"),
            ("长定义", valid_section("长定义", defn="a" * 121), "超过 120 字"),
            ("多句定义", valid_section("多句定义", defn="第一句。第二句。"), "定义须为一句"),
            ("长例外", valid_section("长例外", exc="e" * 121), "超过 120 字"),
            ("长待收口", valid_section("长待收口", todo="t" * 121), "超过 120 字"),
            ("夹说明实现", valid_section("夹说明实现", impl="`src/a.py:f`(加了注释)"), "唯一实现只许反引号"),
            ("夹说明待定", valid_section("夹说明待定", impl="待定,由谁定"), "唯一实现只许反引号"),
            ("带出处半角", valid_section("带出处半角", todo="不改,出处:owner 原话"), "出处"),
            ("带出处全角", valid_section("带出处全角", exc="例外,出处：某处"), "出处"),
            ("带日期", valid_section("带日期", todo="已于 11-15 登记"), "MM-DD"),
            ("断链详情", valid_section("断链详情", detail=True), "详情文件不存在"),
            ("缺字段", "## 缺字段\n- 定义:只有一句。\n", "缺字段:"),
        ]
        table = "# 核心判断\n\n" + "\n\n".join(body for _, body, _ in cases) + "\n"
        self.write(TABLE, table)
        res = self.cli("check")
        self.assertNotEqual(res.returncode, 0)
        for name, _, expected in cases:
            with self.subTest(name=name):
                self.assertIn(expected, res.stdout)
        self.assertIn("docs/judgments/孤儿.md", res.stdout)
        self.assertIn("孤儿", res.stdout)

    def test_symlinked_detail_dir_and_file_are_rejected(self):
        for kind, with_decl in (
            ("dir_symlink", True),
            ("dir_symlink", False),
            ("file_symlink", True),
            ("file_symlink", False),
        ):
            with self.subTest(kind=kind, with_decl=with_decl):
                self.reset_root()
                outside = self.root.parent / "outside"
                outside.mkdir(exist_ok=True)
                (outside / "同区.md").write_text("OUTSIDE_DIR_SECRET\n", encoding="utf-8")
                (outside / "secret.md").write_text("OUTSIDE_FILE_SECRET\n", encoding="utf-8")
                self.write("src/a.py", "def same():\n    pass\n")
                self.write(TABLE, "# 核心判断\n\n" + valid_section("同区", detail=with_decl) + "\n")
                if kind == "dir_symlink":
                    (self.root / "docs" / "judgments").symlink_to(outside)
                else:
                    (self.root / "docs" / "judgments").mkdir(parents=True, exist_ok=True)
                    (self.root / "docs" / "judgments" / "同区.md").symlink_to(outside / "secret.md")
                check_res = self.cli("check")
                self.assertNotEqual(check_res.returncode, 0, check_res.stdout)
                self.assertIn("符号链接", check_res.stdout)
                show_res = self.cli("show", "同区", "--detail")
                self.assertNotEqual(show_res.returncode, 0)
                self.assertIn("符号链接", show_res.stderr)
                combined = show_res.stdout + show_res.stderr
                self.assertNotIn("OUTSIDE_DIR_SECRET", combined)
                self.assertNotIn("OUTSIDE_FILE_SECRET", combined)

        # Also cover docs itself being a symlink to an external directory.
        self.reset_root()
        outside = self.root.parent / "outside"
        outside.mkdir(exist_ok=True)
        (outside / "judgments").mkdir(exist_ok=True)
        (outside / "judgments" / "同区.md").write_text("OUTSIDE_DOCS_SECRET\n", encoding="utf-8")
        (self.root / "docs").symlink_to(outside)
        hook_dir = str(REPO / ".claude" / "hooks")
        sys.path.insert(0, hook_dir)
        try:
            import judgments
            self.assertEqual(
                judgments.check_detail("同区", "`docs/judgments/同区.md`", self.root)[0],
                ["详情路径不许为符号链接: docs/judgments/同区.md"],
            )
            self.assertEqual(
                judgments.orphan_details(self.root, {"docs/judgments/同区.md"}),
                [("docs", "详情路径不许为符号链接")],
            )
        finally:
            sys.path.remove(hook_dir)

    def test_date_boundary_catches_letter_adjacent_without_false_positives(self):
        self.write("src/01-02/a.py", "def same():\n    pass\n")
        self.write("src/a.py", "def same():\n    pass\n")
        bad_cases = [
            ("前紧邻字母", "owner11-15确认"),
            ("后紧邻字母", "11-15owner确认"),
            ("两侧紧邻字母带年", "owner2026-11-15确认"),
            ("双日期斜杠", "11-15/11-16"),
            ("词配斜杠日期", "krapi/11-15"),
            ("反引号纯日期", "`11-15`"),
        ]
        for label, snippet in bad_cases:
            with self.subTest(bad=label):
                self.write(TABLE, "# 核心判断\n\n" + valid_section("同区", todo=snippet) + "\n")
                res = self.cli("check")
                self.assertNotEqual(res.returncode, 0, snippet)
                self.assertIn("MM-DD", res.stdout)

        ok_cases = [
            ("路径实现", valid_section("路径概念", impl="`src/01-02/a.py:same`")),
            ("正文路径", valid_section("正文路径", todo="见 docs/11-15/spec.md")),
            ("带下划线文件名", valid_section("文件名", todo="暂不改 01-02_init.py")),
            ("带前缀版本号", valid_section("版本号一", todo="要求 Python 3.10-12 及 v1.11-15")),
            ("带后缀版本号", valid_section("版本号二", todo="发布 11-15.1 版后清理")),
            ("三段数字串", valid_section("编号串", todo="兼容旧号 01-02-03 与 e78a82c0-11-15-4bec")),
        ]
        self.write(TABLE, "# 核心判断\n\n" + "\n\n".join(sec for _, sec in ok_cases) + "\n")
        res = self.cli("check")
        self.assertEqual((res.returncode, res.stdout, res.stderr), (0, "", ""))


class JudgmentsStopTest(HookCase):
    def setUp(self):
        super().setUp()
        shutil.rmtree(self.root / ".git")
        self.git("init", "-q")
        self.old_long = valid_section("旧长节", defn="旧" * 110, exc="例" * 110, todo="待" * 110)
        self.normal = valid_section("正常节")
        self.write(TABLE, f"# 核心判断\n\n{self.old_long}\n\n{self.normal}\n")
        self.commit()

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True,
                       env={**os.environ, "HOME": str(self.home), "GIT_CONFIG_NOSYSTEM": "1"})

    def commit(self):
        self.git("add", "-A")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.com",
                 "commit", "-q", "--no-verify", "-m", "base")

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def edit_table(self, old="old", new="new", *, error=False, start=BASE + 200):
        return self.claude_call(
            "Edit",
            {"file_path": str(self.root / TABLE), "old_string": old, "new_string": new},
            start, start + 100, error=error,
        )

    def stop(self, *rows, **extra):
        transcript = self.transcript(
            {"type": "user", "timestamp": self.stamp(BASE + 100), "message": {"role": "user", "content": "修改"}},
            *rows,
        )
        return self.run_stop(self.stop_payload(transcript, **extra))

    def stop_text(self, *rows, **extra):
        output = self.stop(*rows, **extra)
        if not output:
            return ""
        parsed = json.loads(output)
        return parsed.get("reason", parsed.get("hookSpecificOutput", {}).get("additionalContext", ""))

    def test_only_changed_violating_sections_are_named(self):
        bad_normal = valid_section("正常节", defn="改" * 150, exc="多" * 130, todo="出处:11-15")
        self.write(TABLE, f"# 核心判断\n\n{self.old_long}\n\n{bad_normal}\n")
        text = self.stop_text(*self.edit_table())
        self.assertIn("正常节", text)
        self.assertIn("核心判断只写一份", text)
        self.assertNotIn("旧长节", text)
        self.assertEqual(len(text.splitlines()), 1)

    def test_unmodified_table_failed_edit_and_previous_turn_stay_silent(self):
        bad_normal = valid_section("正常节", defn="改" * 150, todo="出处:11-15")
        self.write(TABLE, f"# 核心判断\n\n{self.old_long}\n\n{bad_normal}\n")
        # Editing another file does not trigger table-shape reminder.
        other = self.claude_call("Edit", {"file_path": str(self.root / "src/a.py"),
                                          "old_string": "a", "new_string": "b"}, BASE + 200, BASE + 300)
        self.assertEqual(self.stop(*other), "")
        self.assertEqual(self.stop(*self.edit_table(error=True)), "")
        end = {"type": "system", "subtype": "turn_duration", "timestamp": self.stamp(BASE + 400)}
        self.assertEqual(self.stop(*self.edit_table(), end), "")
        self.assertEqual(self.stop(*self.edit_table(), stop_hook_active=True), "")

    def test_head_absent_treats_all_sections_as_changed_and_caps_at_three(self):
        self.git("rm", "-q", TABLE)
        self.commit()
        bad = [valid_section(f"坏节{i}", todo="出处:11-15") for i in range(4)]
        self.write(TABLE, "# 核心判断\n\n" + "\n\n".join(bad) + "\n")
        rows = self.claude_call("Write", {"file_path": str(self.root / TABLE),
                                          "content": (self.root / TABLE).read_text(encoding="utf-8")},
                                BASE + 200, BASE + 300)
        text = self.stop_text(*rows)
        for i in range(3):
            self.assertIn(f"坏节{i}", text)
        self.assertNotIn("坏节3", text)
        self.assertIn("共 4 节", text)

    def test_codex_file_change_and_control_char_escaping(self):
        bad = valid_section("怪\x1b名\t节", todo="出处:owner")
        self.write(TABLE, f"# 核心判断\n\n{self.old_long}\n\n{bad}\n")
        rows = (
            {"type": "event_msg", "timestamp": self.stamp(BASE + 100),
             "payload": {"type": "task_started", "turn_id": "turn-1"}},
            {"type": "event_msg", "timestamp": self.stamp(BASE + 300), "payload": {
                "type": "item_completed", "turn_id": "turn-1", "item": {"type": "FileChange", "changes": {
                    str(self.root / TABLE): {"type": "update", "unified_diff": "@@ -1 +1 @@\n-a\n+b\n"},
                }}}},
        )
        transcript = self.transcript(*rows)
        output = self.run_stop(self.stop_payload(transcript, turn_id="turn-1"))
        reason = json.loads(output)["reason"]
        self.assertEqual(reason.count("\n"), 0, reason)
        self.assertIn("怪\\x1b名\\t节", reason)
        self.assertNotIn("旧长节", reason)

    def test_error_and_timeout_drop_only_table_reminder(self):
        hook_dir = str(REPO / ".claude" / "hooks")
        sys.path.insert(0, hook_dir)
        try:
            import judgments
            import stop_guard
            transcript = self.transcript(
                {"type": "user", "timestamp": self.stamp(BASE + 100), "message": {"role": "user", "content": "修改"}},
                *self.edit_table(),
            )
            payload = self.stop_payload(transcript)
            for err in (TimeoutError("budget"), RuntimeError("boom")):
                with mock.patch.object(judgments, "reminder", side_effect=err), \
                        mock.patch.object(stop_guard, "task_reminder", return_value="[harness] existing"), \
                        mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))):
                    result = stop_guard.main()
                    self.assertEqual(result["hookSpecificOutput"]["additionalContext"], "[harness] existing")
            with mock.patch.object(judgments, "TIME_BUDGET", -1):
                self.assertIsNone(stop_guard.judgment_reminder(payload, self.root, self.root))
        finally:
            sys.path.remove(hook_dir)

    def test_injected_clock_crossing_deadline_in_scan_drops_reminder(self):
        bad_normal = valid_section("正常节", defn="改" * 150, todo="出处:owner")
        self.write(TABLE, f"# 核心判断\n\n{self.old_long}\n\n{bad_normal}\n")
        self.write("docs/judgments/多余.md", "orphan\n")
        transcript = self.transcript(
            {"type": "user", "timestamp": self.stamp(BASE + 100), "message": {"role": "user", "content": "修改"}},
            *self.edit_table(),
        )
        payload = self.stop_payload(transcript)
        hook_dir = str(REPO / ".claude" / "hooks")
        sys.path.insert(0, hook_dir)
        try:
            import judgments
            import stop_guard

            clock_state = {"val": 0.0}
            orig_orphan = judgments.orphan_details

            # Jump monotonic clock past deadline right as orphan_details walks docs/judgments/.
            def slow_orphan(*args, **kwargs):
                clock_state["val"] = 2.0
                return orig_orphan(*args, **kwargs)

            with mock.patch.object(judgments, "orphan_details", side_effect=slow_orphan), \
                    mock.patch.object(time, "monotonic", side_effect=lambda: clock_state["val"]):
                self.assertIsNone(stop_guard.judgment_reminder(payload, self.root, self.root))

            # Also verify a monotonic jump during table_issues/orphan walk without wrapping orphan_details.
            calls = 0

            def advancing_clock():
                nonlocal calls
                calls += 1
                return 0.0 if calls <= 12 else 2.0

            with mock.patch.object(time, "monotonic", side_effect=advancing_clock):
                self.assertIsNone(stop_guard.judgment_reminder(payload, self.root, self.root))

            # Jump clock right after table_issues finishes, testing final pre-return check_time.
            clock_state = {"val": 0.0}
            orig_issues = judgments.table_issues

            def late_issues(*args, **kwargs):
                res = orig_issues(*args, **kwargs)
                clock_state["val"] = 2.0
                return res

            with mock.patch.object(judgments, "table_issues", side_effect=late_issues), \
                    mock.patch.object(time, "monotonic", side_effect=lambda: clock_state["val"]):
                self.assertIsNone(stop_guard.judgment_reminder(payload, self.root, self.root))
        finally:
            sys.path.remove(hook_dir)

    def test_repo_excluded_dir_definition_matches_stop_evidence(self):
        hook_dir = str(REPO / ".claude" / "hooks")
        sys.path.insert(0, hook_dir)
        try:
            import session_start
            import stop_evidence
            entries = {name: sec for name, _, sec in session_start.core_judgment_entries(REPO)}
            defn = entries["项目代码目录"].splitlines()[1]
            self.assertNotIn("VCS", defn)
            for folder in sorted(stop_evidence.EXCLUDED):
                self.assertIn(folder, defn)
        finally:
            sys.path.remove(hook_dir)


if __name__ == "__main__":
    unittest.main()
