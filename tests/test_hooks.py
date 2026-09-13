import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SESSION_START = REPO / ".claude" / "hooks" / "session_start.py"
STOP_GUARD = REPO / ".claude" / "hooks" / "stop_guard.py"


class HookBlackBoxTest(unittest.TestCase):
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
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def run_session(self, payload=None, *, cwd=None, raw=None):
        return self.run_hook(SESSION_START, payload, cwd=cwd, raw=raw)

    def run_stop(self, payload=None, *, cwd=None, raw=None):
        if payload is None and raw is None:
            payload = {"cwd": str(self.root), "stop_hook_active": False}
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

    def stop_fixture(self, *, status="in-progress", marker=True):
        task, spec = self.make_task("active", status)
        marker_path = self.root / ".scratch" / ".session"
        code = self.root / "src" / "changed.py"
        code.parent.mkdir()
        code.write_text("changed = True\n", encoding="utf-8")
        if marker:
            marker_path.write_text("session\n", encoding="utf-8")
        base = 1_900_000_000_000_000_000
        self.set_mtime(spec, base + 100)
        if marker:
            self.set_mtime(marker_path, base + 200)
        self.set_mtime(code, base + 300)
        return task, spec, marker_path, code, base

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

    def test_session_start_no_root_or_no_task_is_silent(self):
        with self.subTest("no scratch root"):
            scratch = self.root / ".scratch"
            scratch.rmdir()
            self.assertEqual(self.run_session(), "")

        with self.subTest("no task"):
            (self.root / ".scratch").mkdir()
            self.assertEqual(self.run_session(), "")

        with self.subTest("single ready task"):
            self.reset_root()
            self.make_task("queued", status="ready-for-agent")
            self.assertEqual(self.run_session(), "")

    def test_session_start_default_cwd_walks_up_and_touches_marker(self):
        _, spec = self.make_task("upward")
        nested = self.root / "one" / "two"
        nested.mkdir(parents=True)
        output = self.run_session(cwd=nested)
        self.assert_session_context(
            output,
            "[harness] Task: upward(.scratch/upward/spec.md)\n"
            "状态: in-progress\n进展: 无",
        )
        self.assertTrue((self.root / ".scratch" / ".session").is_file())
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
            "进展: - 09-10 12:30 done: newest | next: next | 别再试: no",
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
            "当前目录无法唯一匹配 Scope,请明确 Scope 或先收成一个 Task",
        )

        (self.root / ".scratch" / "alpha" / "spec.md").write_text(
            "Status: ready-for-agent\n", encoding="utf-8"
        )
        (self.root / ".scratch" / "zeta" / "spec.md").write_text(
            "Status: done\n", encoding="utf-8"
        )
        self.assertEqual(self.run_session({"cwd": str(self.root)}), "")

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
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")

        for payload in ({"cwd": 3}, {"cwd": []}, {"cwd": None}):
            with self.subTest(payload=payload):
                self.assertEqual(self.run_session(payload), "")

        task, spec = self.make_task("unreadable")
        spec.unlink()
        spec.mkdir()
        self.assertEqual(self.run_session({"cwd": str(self.root)}), "")
        self.assertTrue(task.is_dir())

    def test_stop_guard_no_root_no_task_ready_and_missing_marker_are_silent(self):
        with self.subTest("no scratch root"):
            self.reset_root()
            scratch = self.root / ".scratch"
            scratch.rmdir()
            self.assertEqual(self.run_stop({"cwd": str(self.root), "stop_hook_active": False}), "")

        with self.subTest("no task"):
            self.reset_root()
            self.assertEqual(self.run_stop({"cwd": str(self.root), "stop_hook_active": False}), "")

        with self.subTest("ready task"):
            self.reset_root()
            self.stop_fixture(status="ready-for-agent")
            self.assertEqual(self.run_stop(), "")

        with self.subTest("missing marker"):
            self.reset_root()
            _, _, marker, *_ = self.stop_fixture(marker=False)
            self.assertFalse(marker.exists())
            self.assertEqual(self.run_stop(), "")

    def test_stop_guard_each_condition_and_strict_mtime_edges(self):
        with self.subTest("two active tasks"):
            self.reset_root()
            self.stop_fixture()
            self.make_task("second")
            self.assertEqual(self.run_stop(), "")

        with self.subTest("code is not later than marker"):
            self.reset_root()
            _, spec, marker, code, base = self.stop_fixture()
            self.set_mtime(marker, base + 300)
            self.set_mtime(code, base + 200)
            self.assertGreater(code.stat().st_mtime_ns, spec.stat().st_mtime_ns)
            self.assertEqual(self.run_stop(), "")

        with self.subTest("latest mtime equals marker"):
            self.reset_root()
            _, spec, marker, code, base = self.stop_fixture()
            self.set_mtime(marker, base + 300)
            self.set_mtime(code, base + 300)
            self.assertGreater(code.stat().st_mtime_ns, spec.stat().st_mtime_ns)
            self.assertEqual(self.run_stop(), "")

        with self.subTest("latest mtime equals spec"):
            self.reset_root()
            _, spec, marker, code, base = self.stop_fixture()
            self.set_mtime(marker, base + 200)
            self.set_mtime(spec, base + 300)
            self.set_mtime(code, base + 300)
            self.assertGreater(code.stat().st_mtime_ns, marker.stat().st_mtime_ns)
            self.assertEqual(code.stat().st_mtime_ns, spec.stat().st_mtime_ns)
            self.assertEqual(self.run_stop(), "")

        with self.subTest("latest mtime is earlier than spec"):
            self.reset_root()
            _, spec, marker, code, base = self.stop_fixture()
            self.set_mtime(marker, base + 200)
            self.set_mtime(spec, base + 400)
            self.set_mtime(code, base + 300)
            self.assertGreater(code.stat().st_mtime_ns, marker.stat().st_mtime_ns)
            self.assertLess(code.stat().st_mtime_ns, spec.stat().st_mtime_ns)
            self.assertEqual(self.run_stop(), "")

        with self.subTest("stop hook already active"):
            self.reset_root()
            self.stop_fixture()
            self.assertEqual(
                self.run_stop({"cwd": str(self.root), "stop_hook_active": True}), ""
            )

    def test_stop_guard_all_conditions_block_with_task_name(self):
        self.stop_fixture()
        self.assert_block(self.run_stop(), "active")

    def test_stop_guard_bad_json_non_object_and_bad_field_types_are_silent(self):
        cases = ["", "{", "null", "[]", "1", '"text"']
        for raw in cases:
            with self.subTest(raw=raw):
                result = subprocess.run(
                    [sys.executable, str(STOP_GUARD)],
                    input=raw,
                    text=True,
                    capture_output=True,
                    cwd=str(self.root),
                    timeout=60,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")

        self.stop_fixture()
        for payload in (
            {"cwd": 3, "stop_hook_active": False},
            {"cwd": [], "stop_hook_active": False},
            {"cwd": str(self.root), "stop_hook_active": "false"},
            {"cwd": str(self.root), "stop_hook_active": 0},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.run_stop(payload), "")

        spec = self.root / ".scratch" / "active" / "spec.md"
        spec.unlink()
        spec.mkdir()
        self.assertEqual(self.run_stop(), "")

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
        self.assertIn("无法唯一匹配", context)

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

    def test_stop_guard_scoped_single_ignores_outside_changes(self):
        _, spec = self.make_task("scoped", scope="service/")
        scope = self.root / "service"
        scope.mkdir()
        marker = self.root / ".scratch" / ".session"
        marker.touch()
        outside = self.root / "other" / "changed.py"
        outside.parent.mkdir()
        outside.write_text("changed = True\n", encoding="utf-8")
        base = 1_900_000_000_000_000_000
        self.set_mtime(spec, base + 100)
        self.set_mtime(marker, base + 200)
        self.set_mtime(outside, base + 300)
        self.assertEqual(self.run_stop(), "")

        inside = scope / "changed.py"
        inside.write_text("changed = True\n", encoding="utf-8")
        self.set_mtime(inside, base + 300)
        self.assert_block(self.run_stop(), "scoped")

    def test_stop_guard_selects_scoped_task_from_multiple(self):
        _, api_spec = self.make_task("api", scope="services/api/")
        _, web_spec = self.make_task("web", scope="services/web/")
        _, legacy_spec = self.make_task("legacy")
        api = self.root / "services" / "api"
        web = self.root / "services" / "web"
        api.mkdir(parents=True)
        web.mkdir()
        marker = self.root / ".scratch" / ".session"
        marker.touch()
        changed = api / "changed.py"
        changed.write_text("changed = True\n", encoding="utf-8")
        base = 1_900_000_000_000_000_000
        for path in (api_spec, web_spec, legacy_spec):
            self.set_mtime(path, base + 100)
        self.set_mtime(marker, base + 200)
        self.set_mtime(changed, base + 300)
        self.assert_block(
            self.run_stop({"cwd": str(api), "stop_hook_active": False}), "api"
        )
        self.assertEqual(
            self.run_stop({"cwd": str(self.root), "stop_hook_active": False}), ""
        )

        _, inner_spec = self.make_task("inner", scope="services/api/handlers/")
        handlers = api / "handlers"
        handlers.mkdir()
        self.set_mtime(inner_spec, base + 100)
        self.assertEqual(
            self.run_stop({"cwd": str(handlers), "stop_hook_active": False}), ""
        )

    def test_stop_guard_scoped_excluded_directory_remains_excluded(self):
        _, spec = self.make_task("config", scope=".claude/work/")
        marker = self.root / ".scratch" / ".session"
        marker.touch()
        changed = self.root / ".claude" / "work" / "changed.py"
        changed.parent.mkdir(parents=True)
        changed.write_text("changed = True\n", encoding="utf-8")
        base = 1_900_000_000_000_000_000
        self.set_mtime(spec, base + 100)
        self.set_mtime(marker, base + 200)
        self.set_mtime(changed, base + 300)
        self.assertEqual(self.run_stop(), "")

    def test_invalid_scopes_fail_open_for_both_hooks(self):
        def assert_invalid(scope, changed):
            _, spec = self.make_task("invalid", scope=scope)
            marker = self.root / ".scratch" / ".session"
            marker.touch()
            changed.parent.mkdir(parents=True, exist_ok=True)
            changed.write_text("changed = True\n", encoding="utf-8")
            base = 1_900_000_000_000_000_000
            self.set_mtime(spec, base + 100)
            self.set_mtime(marker, base + 200)
            self.set_mtime(changed, base + 300)
            payload = {"cwd": str(self.root), "source": "resume"}
            self.assertEqual(self.run_session(payload), "")
            payload["stop_hook_active"] = False
            self.assertEqual(self.run_stop(payload), "")

        with self.subTest(scope="empty"):
            assert_invalid("", self.root / "changed.py")

        for kind in ("traversal", "absolute", "symlink"):
            with self.subTest(scope=kind), tempfile.TemporaryDirectory(
                    dir=self.root.parent) as outside:
                self.reset_root()
                outside = Path(outside)
                changed = outside / "changed.py"
                if kind == "traversal":
                    scope = f"../{outside.name}/"
                elif kind == "absolute":
                    scope = f"{outside}/"
                else:
                    (self.root / "escape").symlink_to(
                        outside, target_is_directory=True)
                    scope = "escape/"
                assert_invalid(scope, changed)

    def test_stop_guard_any_spec_read_failure_releases_a_real_block(self):
        self.stop_fixture()
        broken = self.root / ".scratch" / "broken"
        broken.mkdir()
        (broken / "spec.md").symlink_to("missing.md")
        self.assertEqual(self.run_stop(), "")

        self.reset_root()
        self.stop_fixture()
        invalid = self.root / ".scratch" / "invalid"
        invalid.mkdir()
        (invalid / "spec.md").write_bytes(b"Status: in-progress\n\xff")
        self.assertEqual(self.run_stop(), "")

    def test_stop_guard_excludes_named_directories_at_any_depth(self):
        self.stop_fixture()
        excluded = (".scratch", ".git", ".claude", ".codex", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", "target")
        for name in excluded:
            path = self.root / "nested" / name / "deeper" / "ignored.txt"
            path.parent.mkdir(parents=True)
            path.write_text("ignored\n", encoding="utf-8")
            self.set_mtime(path, 1_900_000_000_000_000_500)
        allowed = self.root / "src" / "changed.py"
        self.set_mtime(allowed, 1_900_000_000_000_000_100)
        marker = self.root / ".scratch" / ".session"
        self.set_mtime(marker, 1_900_000_000_000_000_200)
        spec = self.root / ".scratch" / "active" / "spec.md"
        self.set_mtime(spec, 1_900_000_000_000_000_100)
        self.assertEqual(self.run_stop(), "")

    def test_stop_guard_20000_files_allowed_and_20001_files_pass_through(self):
        _, _, _, code, _ = self.stop_fixture()
        code.unlink()
        fill = self.root / "files"
        fill.mkdir()
        first = None
        for index in range(20_000):
            path = fill / f"{index:05d}.txt"
            path.write_text("x", encoding="utf-8")
            if first is None:
                first = path

        base = 1_900_000_100_000_000_000
        spec = self.root / ".scratch" / "active" / "spec.md"
        marker = self.root / ".scratch" / ".session"
        self.set_mtime(spec, base + 100)
        self.set_mtime(marker, base + 200)
        self.set_mtime(first, base + 300)
        self.assert_block(self.run_stop(), "active")

        extra = fill / "20000.txt"
        extra.write_text("x", encoding="utf-8")
        self.set_mtime(extra, base + 300)
        self.assertEqual(self.run_stop(), "")


if __name__ == "__main__":
    unittest.main()


class SessionMarkerSourceTest(unittest.TestCase):
    """SessionStart 的 source 决定要不要重置会话标记。"""

    def _run(self, root, source):
        payload = {"cwd": str(root), "hook_event_name": "SessionStart"}
        if source is not None:
            payload["source"] = source
        return subprocess.run([sys.executable, str(SESSION_START)], input=json.dumps(payload),
                              capture_output=True, text=True)

    def _fixture(self):
        d = tempfile.mkdtemp()
        root = Path(d)
        (root / ".scratch" / "t1").mkdir(parents=True)
        (root / ".scratch" / "t1" / "spec.md").write_text("Status: in-progress\n\n## 进展\n", encoding="utf-8")
        marker = root / ".scratch" / ".session"
        marker.touch()
        os.utime(marker, ns=(1_000_000_000, 1_000_000_000))
        return root, marker

    def test_compact_and_resume_keep_existing_marker(self):
        for source in ("compact", "resume"):
            root, marker = self._fixture()
            r = self._run(root, source)
            self.assertEqual(r.returncode, 0)
            self.assertEqual(marker.stat().st_mtime_ns, 1_000_000_000, source)
            self.assertIn("harness-v1" if False else "t1", r.stdout)

    def test_startup_clear_and_missing_source_reset_marker(self):
        for source in ("startup", "clear", None):
            root, marker = self._fixture()
            r = self._run(root, source)
            self.assertEqual(r.returncode, 0)
            self.assertGreater(marker.stat().st_mtime_ns, 1_000_000_000, str(source))

    def test_compact_without_marker_creates_it(self):
        root, marker = self._fixture()
        marker.unlink()
        r = self._run(root, "compact")
        self.assertEqual(r.returncode, 0)
        self.assertTrue(marker.is_file())
