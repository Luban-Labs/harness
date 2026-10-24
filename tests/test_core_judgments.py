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
                        "### 同区\n", "```md\n## 同区\n```\n", b"\xff\xfe## \xe5\n"):
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
        for copy in ("task_scope", "read_tasks", "spec_kind"):
            self.assertNotIn(copy, defined["stop_guard"])


if __name__ == "__main__":
    unittest.main()
