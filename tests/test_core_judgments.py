"""Core-judgment table: the SessionStart concept line, install, migration, and harness's own table."""

import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from hook_support import REPO, SESSION_START, HookCase


sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO))
import init  # noqa: E402


TABLE = "docs/rules/core-judgments.md"
LINE = "[harness] 核心判断表 docs/rules/core-judgments.md:同区、同场;新写或改判断前先查表"


class ConceptLineTest(HookCase):
    def table(self, content):
        path = self.root / TABLE
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return path

    def ready(self):
        folder = self.root / ".scratch" / "ready"
        folder.mkdir()
        (folder / "spec.md").write_text("Status: ready-for-agent\n", encoding="utf-8")

    def context(self, **payload):
        output = self.run_session({"cwd": str(self.root), "session_id": "abcdefgh-1234", **payload})
        return json.loads(output)["hookSpecificOutput"]["additionalContext"] if output else ""

    def test_non_empty_board_ends_with_concepts_on_startup_and_compact(self):
        self.ready()
        self.table("# 核心判断\n\n说明。\n\n## 同区\n- 定义:x\n\n## 同场\n- 定义:y\n")
        for source in ("startup", "compact"):
            with self.subTest(source=source):
                lines = self.context(source=source).splitlines()
                self.assertEqual(lines[-1], LINE)
                self.assertTrue(lines[-2].startswith("[harness] 待开工 Task: ready;"), lines)
                self.assertEqual(sum("核心判断表" in line for line in lines), 1)

    def test_headings_after_a_closed_fence_are_listed(self):
        self.ready()
        self.table("~~~md\n## 示例\n~~~\n````\n```\n## 示例\n````\n## 同区\n## 同场\n")
        self.assertEqual(self.context().splitlines()[-1], LINE)

    def test_concept_line_lists_at_most_twenty_names(self):
        self.ready()
        names = [f"概念{n}" for n in range(1, 22)]
        self.table("".join(f"## {name}\n" for name in names))
        line = self.context().splitlines()[-1]
        self.assertEqual(line, f"[harness] 核心判断表 {TABLE}:{'、'.join(names[:20])} 等 21 个;新写或改判断前先查表")
        self.table("".join(f"## {name}\n" for name in names[:20]))
        self.assertEqual(self.context().splitlines()[-1],
                         f"[harness] 核心判断表 {TABLE}:{'、'.join(names[:20])};新写或改判断前先查表")

    def test_empty_board_stays_zero_bytes_with_a_filled_table(self):
        self.table("# 核心判断\n\n## 同区\n")
        archived = self.root / ".scratch" / "archive" / "closed"
        archived.mkdir(parents=True)
        (archived / "spec.md").write_text("Status: done\n\n## 验收\n- [x] [你] 已看\n", encoding="utf-8")
        for source in ("startup", "compact", None):
            with self.subTest(source=source):
                self.assertEqual(self.run_session({"cwd": str(self.root), "source": source}), "")

    def test_missing_empty_or_unreadable_table_adds_nothing(self):
        self.ready()
        baseline = self.context()
        self.assertTrue(baseline)
        self.assertNotIn("核心判断表", baseline)
        for content in (init.empty_core_judgments(), "# 核心判断\n\n说明。\n", "## \n",
                        "### 同区\n", "```md\n## 同区\n```\n", "~~~md\n## 同区\n~~~\n",
                        "````md\n```\n## 同区\n```\n````\n", "```md\n~~~\n## 同区\n", b"\xff\xfe## \xe5\n"):
            with self.subTest(content=content):
                self.table(content)
                self.assertEqual(self.context(), baseline)
        path = self.root / TABLE
        path.unlink()
        path.mkdir()
        self.assertEqual(self.context(), baseline)

    def test_board_command_for_the_owner_carries_no_concept_line(self):
        self.ready()
        self.table("## 同区\n")
        result = subprocess.run(
            [sys.executable, str(SESSION_START), "--board", "--cwd", str(self.root)],
            input="", text=True, capture_output=True, cwd=self.root, timeout=60,
            env={**os.environ, "HOME": str(self.home), "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        self.assertIn("待开工 Task: ready;", result.stdout)
        self.assertNotIn("核心判断表", result.stdout)


class InstallTableTest(unittest.TestCase):
    def test_empty_table_is_the_template_description_without_concepts(self):
        text = init.empty_core_judgments()
        template = (REPO / "templates" / "core-judgments.md").read_text(encoding="utf-8")
        self.assertTrue(template.startswith(text.rstrip("\n")))
        self.assertTrue(text.startswith("# 核心判断\n"))
        self.assertIn("docs/rules/harness.md「核心判断只写一份」", text)
        self.assertEqual([line for line in text.splitlines() if line.startswith("## ")], [])
        self.assertNotIn("同区", text)
        self.assertIn("## 同区", template)

    def test_init_creates_empty_table_and_never_overwrites_one(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d)
            result = subprocess.run([sys.executable, str(REPO / "init.py"), d],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(f"+ {TABLE}", result.stdout)
            self.assertEqual((target / TABLE).read_text(encoding="utf-8"), init.empty_core_judgments())
            self.assertIn("| docs/rules/core-judgments.md |", (target / "AGENTS.md").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as d:
            target = Path(d)
            (target / "docs" / "rules").mkdir(parents=True)
            (target / TABLE).write_text("# 项目的表\n\n## 同区\n", encoding="utf-8")
            (target / "AGENTS.md").write_text("# 我的规则\n", encoding="utf-8")
            for _ in range(2):
                result = subprocess.run([sys.executable, str(REPO / "init.py"), d],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual((target / TABLE).read_text(encoding="utf-8"), "# 项目的表\n\n## 同区\n")
                self.assertIn(f"= {TABLE}", result.stdout)
                self.assertIn("新写或改一个判断 → docs/rules/core-judgments.md", result.stdout)

    def test_migration_creates_the_routed_table_and_keeps_an_existing_one(self):
        fixture = REPO / "tests" / "trellis_fixture.py"
        migrate = REPO / "migrate_trellis.py"
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        args = ("--scope", "active-build=src/build/", "--scope", "active-review=src/review/",
                "--date", "2026-09-13", "--apply")
        for existing in (None, "# 项目的表\n\n## 同区\n"):
            with self.subTest(existing=existing), tempfile.TemporaryDirectory() as d:
                target = Path(d)
                made = subprocess.run([sys.executable, str(fixture), d], capture_output=True, text=True, env=env)
                self.assertEqual(made.returncode, 0, made.stdout + made.stderr)
                if existing is not None:
                    (target / "docs" / "rules").mkdir(parents=True, exist_ok=True)
                    (target / TABLE).write_text(existing, encoding="utf-8")
                result = subprocess.run([sys.executable, str(migrate), d, *args],
                                        capture_output=True, text=True, env=env)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("| docs/rules/core-judgments.md |", (target / "AGENTS.md").read_text(encoding="utf-8"))
                self.assertEqual((target / TABLE).read_text(encoding="utf-8"),
                                 init.empty_core_judgments() if existing is None else existing)
                self.assertIn(f"INSTALL {TABLE}" if existing is None else f"KEEP {TABLE}", result.stdout)

    def test_migration_adds_fixed_routes_an_existing_routing_table_lacks(self):
        fixture = REPO / "tests" / "trellis_fixture.py"
        migrate = REPO / "migrate_trellis.py"
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        args = ("--scope", "active-build=src/build/", "--scope", "active-review=src/review/",
                "--date", "2026-09-13", "--apply")
        owned = ("# 规则\n\n## 路由表\n\n| 做什么 | 读 |\n| --- | --- |\n"
                 "| 开工或收尾 | docs/rules/harness.md |\n| 改接口 | docs/api.md |\n\n## 其他\n\n正文\n")
        for content, expected in (
            (owned, "| 改接口 | docs/api.md |\n| 改动会改变"),
            ("# 规则\n\n## 路由表\n\n正文\n", "## 路由表\n\n| 做什么 / 改到哪 | 读 |"),
        ):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as d:
                target = Path(d)
                made = subprocess.run([sys.executable, str(fixture), d], capture_output=True, text=True, env=env)
                self.assertEqual(made.returncode, 0, made.stdout + made.stderr)
                (target / "AGENTS.md").write_text(content, encoding="utf-8")
                result = subprocess.run([sys.executable, str(migrate), d, *args],
                                        capture_output=True, text=True, env=env)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                text = (target / "AGENTS.md").read_text(encoding="utf-8")
                self.assertIn(expected, text)
                for target_cell in ("| docs/rules/harness.md |", "| docs/rules/harness.md「改动的影响面」 |",
                                    "| docs/rules/core-judgments.md |"):
                    self.assertEqual(text.count(target_cell), 1, text)
                self.assertEqual(text.count("路由表"), 1, text)


class SharedSpecReadingTest(HookCase):
    """The board and Stop read a spec's sections and 待结案 through one implementation."""

    SESSION = "cb260c48-3465-481c-9e57-cea155732e77"

    def spec(self, text):
        folder = self.root / ".scratch" / "active"
        folder.mkdir(exist_ok=True)
        (folder / "spec.md").write_text(f"Status: in-progress\n会话: {self.SESSION}\n\n# Task\n\n{text}",
                                        encoding="utf-8")

    def board_line(self):
        output = self.run_session({"cwd": str(self.root), "session_id": "other-session"})
        context = json.loads(output)["hookSpecificOutput"]["additionalContext"]
        return next(line for line in context.splitlines() if line.startswith("- active ·"))

    def stop(self):
        output = self.run_stop({"cwd": str(self.root), "stop_hook_active": False, "session_id": self.SESSION})
        return json.loads(output)["hookSpecificOutput"]["additionalContext"] if output else ""

    def test_extra_space_after_hashes_is_the_same_section_for_both(self):
        self.spec("##  验收\n- [x] [我] test\n- [ ] [你] look\n\n##  进展\n- 10-25 09:00 done: x | next: 你: look\n")
        self.assertIn("· 待结案: look", self.board_line())
        self.assertIn("[我] 验收项已全部勾上", self.stop())

    def test_top_heading_ends_progress_for_both(self):
        short = "- 10-25 09:00 done: x | next: 你: look"
        long = "- 10-25 10:00 " + "字" * 200 + " | next: 你: look"
        self.spec(f"## 验收\n- [ ] [我] test\n\n## 进展\n{short}\n# 附录\n{long}\n")
        self.assertIn("· 你: look", self.board_line())
        self.assertEqual(self.stop(), "")
        self.spec(f"## 验收\n- [ ] [我] test\n\n## 进展\n{short}\n{long}\n# 附录\n")
        self.assertIn("进展最后一行超过 200 字", self.stop())


class HarnessTableTest(unittest.TestCase):
    MODULES = {
        "session_start": REPO / ".claude" / "hooks" / "session_start.py",
        "stop_guard": REPO / ".claude" / "hooks" / "stop_guard.py",
        "stop_evidence": REPO / ".claude" / "hooks" / "stop_evidence.py",
        "init": REPO / "init.py",
        "migrate_trellis": REPO / "migrate_trellis.py",
    }

    def test_each_unique_implementation_exists_once(self):
        defined = {
            name: {node.name for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                   if isinstance(node, ast.FunctionDef)}
            for name, path in self.MODULES.items()
        }
        text = (REPO / TABLE).read_text(encoding="utf-8")
        concepts = re.findall(r"^## (.+)$", text, flags=re.M)
        implementations = re.findall(r"^- 唯一实现:\s*`?(\w+)\.(\w+)", text, flags=re.M)
        self.assertEqual(len(implementations), len(concepts))
        for module, function in implementations:
            with self.subTest(function=f"{module}.{function}"):
                self.assertIn(function, defined[module])
                self.assertEqual([name for name, names in defined.items()
                                  if name != module and function in names], [])
        for copy in ("task_scope", "read_tasks", "spec_kind", "spec_sections", "section_lines", "ready_to_close"):
            self.assertNotIn(copy, defined["stop_guard"])


if __name__ == "__main__":
    unittest.main()
