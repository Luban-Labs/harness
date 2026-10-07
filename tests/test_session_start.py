import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hook_support import SESSION_START, HookCase


class SessionStartTest(HookCase):
    def test_session_start_no_root_or_no_task_is_silent(self):
        with self.subTest("no scratch root"):
            scratch = self.root / ".scratch"
            scratch.rmdir()
            self.assertEqual(self.run_session(), "")

        with self.subTest("no task"):
            (self.root / ".scratch").mkdir()
            self.assertEqual(self.run_session(), "")

        with self.subTest("done task only"):
            self.reset_root()
            self.make_task("finished", status="done")
            self.assertEqual(self.run_session(), "")

    def test_session_start_default_cwd_walks_up_without_marker(self):
        _, spec = self.make_task("upward")
        nested = self.root / "one" / "two"
        nested.mkdir(parents=True)
        output = self.run_session(cwd=nested)
        self.assert_session_context(
            output,
            "[harness] Task: upward(.scratch/upward/spec.md)\n"
            "状态: in-progress\n进展: 无",
        )
        self.assertFalse((self.root / ".scratch" / ".session").exists())
        self.assertTrue(spec.is_file())

    def test_session_start_one_active_with_and_without_progress(self):
        self.make_task("empty", progress=[])
        output = self.run_session({"cwd": str(self.root)})
        self.assert_session_context(
            output,
            "[harness] Task: empty(.scratch/empty/spec.md)\n"
            "状态: in-progress\n进展: 无",
        )

        (self.root / ".scratch" / "empty").rename(self.root / ".scratch" / "old")
        (self.root / ".scratch" / "old" / "spec.md").write_text(
            "Status: ready-for-agent\n", encoding="utf-8"
        )
        self.make_task(
            "with-progress",
            progress=[
                "- 09-10 12:00 done: first | next: second | 别再试: old",
                "",
                "- 09-10 12:30 done: newest | next: next | 别再试: no",
                "",
                "## 备注",
                "- 这行不属于进展段",
            ],
        )
        output = self.run_session({"cwd": str(self.root)})
        self.assert_session_context(
            output,
            "[harness] Task: with-progress(.scratch/with-progress/spec.md)\n"
            "状态: in-progress\n"
            "进展: - 09-10 12:30 done: newest | next: next | 别再试: no\n"
            "[harness] 待开工 Task: old;需求相关时先读 .scratch/<名>/spec.md",
        )

    def test_session_start_multiple_is_sorted_and_archive_is_ignored(self):
        self.make_task("zeta")
        self.make_task("alpha")
        archived = self.root / ".scratch" / "archive" / "archived"
        archived.mkdir(parents=True)
        (archived / "spec.md").write_text("Status: in-progress\n", encoding="utf-8")
        output = self.run_session({"cwd": str(self.root)})
        self.assert_session_context(
            output,
            "[harness] 有 2 个 in-progress Task: "
            "alpha(Scope: all-project), zeta(Scope: all-project);"
            "进对应 Scope 的目录开会话可注入该 Task 的详情",
        )

        (self.root / ".scratch" / "alpha" / "spec.md").write_text(
            "Status: ready-for-agent\n", encoding="utf-8"
        )
        (self.root / ".scratch" / "zeta" / "spec.md").write_text(
            "Status: done\n", encoding="utf-8"
        )
        self.assert_session_context(
            self.run_session({"cwd": str(self.root)}),
            "[harness] 待开工 Task: alpha;需求相关时先读 .scratch/<名>/spec.md",
        )

    def test_session_start_ready_tasks_alone_and_after_active_context(self):
        ready = "[harness] 待开工 Task: queued;需求相关时先读 .scratch/<名>/spec.md"
        self.make_task("queued", status="ready-for-agent")
        archived = self.root / ".scratch" / "archive" / "old-ready"
        archived.mkdir(parents=True)
        (archived / "spec.md").write_text("Status: ready-for-agent\n", encoding="utf-8")
        with self.subTest("ready only"):
            self.assert_session_context(self.run_session({"cwd": str(self.root)}), ready)

        with self.subTest("one active"):
            self.make_task("active")
            self.assert_session_context(
                self.run_session({"cwd": str(self.root)}),
                "[harness] Task: active(.scratch/active/spec.md)\n"
                f"状态: in-progress\n进展: 无\n{ready}",
            )

        with self.subTest("multiple active"):
            self.make_task("second")
            self.assert_session_context(
                self.run_session({"cwd": str(self.root)}),
                "[harness] 有 2 个 in-progress Task: "
                "active(Scope: all-project), second(Scope: all-project);"
                f"进对应 Scope 的目录开会话可注入该 Task 的详情\n{ready}",
            )

    def test_session_start_ready_list_is_capped_at_five(self):
        for index in range(1, 8):
            self.make_task(f"r{index}", status="ready-for-agent")
        self.assert_session_context(
            self.run_session({"cwd": str(self.root)}),
            "[harness] 待开工 Task: r1, r2, r3, r4, r5 等 7 个;"
            "需求相关时先读 .scratch/<名>/spec.md",
        )

    def test_session_start_ready_name_with_newline_is_skipped(self):
        self.make_task("bad\nname", status="ready-for-agent")
        self.make_task("active")
        self.assert_session_context(
            self.run_session({"cwd": str(self.root)}),
            "[harness] Task: active(.scratch/active/spec.md)\n"
            "状态: in-progress\n进展: 无",
        )

    def test_session_start_bad_json_non_object_bad_types_and_read_failure_are_silent(self):
        cases = ["", "{", "null", "[]", "1", '"text"']
        for raw in cases:
            with self.subTest(raw=raw):
                result = subprocess.run(
                    [sys.executable, str(SESSION_START)],
                    input=raw,
                    text=True,
                    capture_output=True,
                    cwd=str(self.root),
                    timeout=60,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                self.assertEqual(result.stdout, "")

        for payload in ({"cwd": 3}, {"cwd": []}, {"cwd": None}):
            with self.subTest(payload=payload):
                self.assertEqual(self.run_session(payload), "")

        task, spec = self.make_task("unreadable")
        spec.unlink()
        spec.mkdir()
        self.assertEqual(self.run_session({"cwd": str(self.root)}), "")
        self.assertTrue(task.is_dir())

    def test_session_start_selects_one_scoped_task_by_cwd_components(self):
        self.make_task("api", scope="services/api/")
        self.make_task("web", scope="services/web/")
        self.make_task("legacy")
        cwd = self.root / "services" / "api" / "handlers"
        cwd.mkdir(parents=True)
        output = self.run_session({"cwd": str(cwd)})
        self.assert_session_context(
            output,
            "[harness] Task: api(.scratch/api/spec.md)\n"
            "状态: in-progress\n进展: 无",
        )

        sibling = self.root / "services" / "api-old"
        sibling.mkdir()
        output = self.run_session({"cwd": str(sibling)})
        context = json.loads(output)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("api(Scope: services/api/)", context)
        self.assertIn("web(Scope: services/web/)", context)
        self.assertIn("legacy(Scope: all-project)", context)
        self.assertIn("进对应 Scope 的目录", context)

    def test_session_start_overlap_and_missing_scope_summarize_all_tasks(self):
        self.make_task("all")
        self.make_task("outer", scope="area/")
        self.make_task("inner", scope="area/inner/")
        cwd = self.root / "area" / "inner" / "work"
        cwd.mkdir(parents=True)
        output = self.run_session({"cwd": str(cwd)})
        context = json.loads(output)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("all(Scope: all-project)", context)
        self.assertIn("outer(Scope: area/)", context)
        self.assertIn("inner(Scope: area/inner/)", context)


class SessionMarkerSourceTest(unittest.TestCase):
    """SessionStart 各来源均不创建或改动旧会话标记。"""

    def _run(self, root, source):
        payload = {"cwd": str(root), "hook_event_name": "SessionStart"}
        if source is not None:
            payload["source"] = source
        return subprocess.run([sys.executable, str(SESSION_START)], input=json.dumps(payload),
                              capture_output=True, text=True,
                              env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})

    def _fixture(self):
        root = Path(tempfile.mkdtemp())
        (root / ".scratch" / "t1").mkdir(parents=True)
        (root / ".scratch" / "t1" / "spec.md").write_text("Status: in-progress\n\n## 进展\n", encoding="utf-8")
        marker = root / ".scratch" / ".session"
        marker.touch()
        os.utime(marker, ns=(1_000_000_000, 1_000_000_000))
        return root, marker

    def test_all_sources_keep_existing_marker_and_injection(self):
        for source in ("startup", "clear", "compact", "resume", None):
            root, marker = self._fixture()
            try:
                r = self._run(root, source)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(r.stderr, "")
                self.assertEqual(marker.stat().st_mtime_ns, 1_000_000_000, source)
                self.assertEqual(json.loads(r.stdout), {"hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": "[harness] Task: t1(.scratch/t1/spec.md)\n"
                                         "状态: in-progress\n进展: 无"}})
            finally:
                import shutil
                shutil.rmtree(root)

    def test_all_sources_leave_missing_marker_missing(self):
        for source in ("startup", "clear", "compact", "resume", None):
            root, marker = self._fixture()
            try:
                marker.unlink()
                r = self._run(root, source)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(r.stderr, "")
                self.assertFalse(marker.exists(), source)
                self.assertIn("t1", r.stdout)
            finally:
                import shutil
                shutil.rmtree(root)


if __name__ == "__main__":
    unittest.main()
