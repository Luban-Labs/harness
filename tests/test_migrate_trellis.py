import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATE = ROOT / "migrate_trellis.py"
FIXTURE = ROOT / "tests" / "trellis_fixture.py"
FIXED_DATE = "2026-09-13"
LEGACY_HOOKS = (
    "session-start.py",
    "inject-workflow-state.py",
    "inject-subagent-context.py",
)
SCOPES = (
    "--scope",
    "active-build=src/build/",
    "--scope",
    "active-review=src/review/",
)


def python_env(**extra):
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(extra)
    return env


def run_python(script, *args, env=None):
    return subprocess.run(
        [sys.executable, str(script), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=60,
        env=python_env() if env is None else env,
    )


def snapshot(root):
    """Return bytes, links, modes, and mtimes without following symlinks."""
    root = Path(root)
    root_info = root.lstat()
    result = {".": ("dir", stat.S_IMODE(root_info.st_mode), root_info.st_mtime_ns)}
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs.sort()
        files.sort()
        for name in dirs + files:
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            info = path.lstat()
            common = (stat.S_IMODE(info.st_mode), info.st_mtime_ns)
            if path.is_symlink():
                value = ("link", os.readlink(path), *common)
            elif path.is_dir():
                value = ("dir", *common)
            else:
                value = ("file", path.read_bytes(), *common)
            result[relative] = value
    return result


def hook_commands(data):
    return [
        handler.get("command", "")
        for groups in data.get("hooks", {}).values()
        for group in groups
        for handler in group.get("hooks", [])
    ]


def template_routing_table():
    lines = (ROOT / "templates/AGENTS.md").read_text(encoding="utf-8").splitlines()
    start = next(
        index
        for index, line in enumerate(lines)
        if line.lstrip("#").strip() == "路由表"
    )
    block = []
    for line in lines[start:]:
        if block and line.startswith("#"):
            break
        if "[示例：" not in line and "[占位：" not in line:
            block.append(line)
    return "\n".join(block).strip()


class FixtureCliTest(unittest.TestCase):
    def test_fixture_cli_requires_an_existing_empty_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = run_python(FIXTURE, root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((root / ".trellis/tasks/plan-next/task.json").is_file())
            self.assertTrue((root / ".trellis/tasks/active-review/task.json").is_file())

            before = snapshot(root)
            result = run_python(FIXTURE, root)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(snapshot(root), before)

        missing = Path(tempfile.gettempdir()) / "trellis-fixture-does-not-exist"
        result = run_python(FIXTURE, missing)
        self.assertEqual(result.returncode, 1)


class MigrateTrellisBlackBoxTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        result = run_python(FIXTURE, self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def tearDown(self):
        self.temp.cleanup()

    def run_migrate(self, *args, root=None, env=None):
        target = self.root if root is None else Path(root)
        return run_python(MIGRATE, target, *args, env=env)

    def migrate_args(self, *extra):
        return (*SCOPES, "--date", FIXED_DATE, *extra)

    def assert_rejected_without_writes(self, *args):
        before = snapshot(self.root)
        result = self.run_migrate(*args)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(snapshot(self.root), before)
        return result

    def apply_fixture(self):
        result = self.run_migrate(*self.migrate_args("--apply"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_help_documents_the_public_cli(self):
        result = run_python(MIGRATE, "--help")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        help_text = result.stdout + result.stderr
        self.assertIn("--apply", help_text)
        self.assertIn("--scope", help_text)
        self.assertIn("--date", help_text)

    def test_dry_run_prints_complete_plan_and_changes_no_bytes_links_or_mtimes(self):
        before = snapshot(self.root)
        result = self.run_migrate(*self.migrate_args())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(snapshot(self.root), before)

        for text in (
            ".scratch/plan-next/spec.md",
            ".scratch/active-build/spec.md",
            ".scratch/active-review/spec.md",
            ".scratch/archive/completed-one/spec.md",
            ".scratch/archive/00-bootstrap-guidelines/spec.md",
            "docs/archive/trellis/.trellis/templates/task.md",
            "docs/archive/trellis/platform/.claude/hooks/session-start.py",
            ".claude/settings.json",
            ".codex/hooks.json",
            ".codex/config.toml",
            "AGENTS.md",
            ".gitattributes",
            ".gitignore",
            "trusted_hash",
        ):
            self.assertIn(text, result.stdout)

    def test_apply_maps_all_statuses_scopes_and_task_documents(self):
        source_files = {
            path.relative_to(self.root / ".trellis/tasks/plan-next").as_posix(): path.read_bytes()
            for path in (self.root / ".trellis/tasks/plan-next").rglob("*")
            if path.is_file()
        }
        self.apply_fixture()

        expected = {
            "plan-next": (self.root / ".scratch/plan-next", "ready-for-agent"),
            "active-build": (self.root / ".scratch/active-build", "in-progress"),
            "active-review": (self.root / ".scratch/active-review", "in-progress"),
            "completed-one": (self.root / ".scratch/archive/completed-one", "done"),
            "00-bootstrap-guidelines": (
                self.root / ".scratch/archive/00-bootstrap-guidelines",
                "done",
            ),
        }
        for name, (directory, status_value) in expected.items():
            with self.subTest(task=name):
                lines = (directory / "spec.md").read_text(encoding="utf-8").splitlines()
                self.assertEqual(lines[0], f"Status: {status_value}")
        self.assertEqual(
            (self.root / ".scratch/archive/completed-one/spec.md").read_text().splitlines()[1],
            "# completed-one",
        )

        plan_spec = (self.root / ".scratch/plan-next/spec.md").read_text(encoding="utf-8")
        self.assertEqual(plan_spec.splitlines()[1], "# Plan the next release")
        self.assertIn("来源: Trellis 任务 .trellis/tasks/plan-next", plan_spec)
        self.assertIn("原状态 planning", plan_spec)
        self.assertIn(f"迁移于 {FIXED_DATE}", plan_spec)
        self.assertRegex(
            plan_spec,
            r"- 09-13 \d{2}:\d{2} done: 从 Trellis 迁入\(原状态 planning\)"
            r" \| next: 按 prd\.md 继续 \| 别再试: 无",
        )
        for document, role in (
            ("prd.md", "需求与验收"),
            ("design-api.md", "设计"),
            ("implementation.md", "实施步骤"),
            ("research/notes.md", "调研"),
            ("dispatch/worker.md", "派工包"),
            ("协作单-示例.md", "协作单"),
            ("context.jsonl", "Trellis 上下文清单,已失效仅存档"),
            ("notes.txt", "原样保留"),
            ("assets/payload.bin", "原样保留"),
            ("trellis-task.json", "原样保留"),
        ):
            self.assertIn(f"{document} — {role}", plan_spec)

        for relative, payload in source_files.items():
            destination = "trellis-task.json" if relative == "task.json" else relative
            self.assertEqual(
                (self.root / ".scratch/plan-next" / destination).read_bytes(),
                payload,
                destination,
            )
        active_build = (self.root / ".scratch/active-build/spec.md").read_text()
        active_review = (self.root / ".scratch/active-review/spec.md").read_text()
        self.assertEqual(active_build.splitlines()[:2], ["Status: in-progress", "Scope: src/build/"])
        self.assertEqual(active_review.splitlines()[:2], ["Status: in-progress", "Scope: src/review/"])
        bootstrap = (self.root / ".scratch/archive/00-bootstrap-guidelines/spec.md").read_text()
        self.assertIn("Trellis 拆除,规范改由 docs/rules/ 承接", bootstrap)
        self.assertFalse((self.root / ".trellis").exists())

    def test_apply_archives_every_legacy_payload_and_preserves_unknown_files(self):
        trellis_payloads = {
            path.relative_to(self.root / ".trellis").as_posix(): path.read_bytes()
            for path in (self.root / ".trellis").rglob("*")
            if path.is_file() and "/tasks/" not in f"/{path.relative_to(self.root / '.trellis').as_posix()}"
        }
        platform_sources = (
            ".claude/hooks/session-start.py",
            ".claude/hooks/trellis_guard.py",
            ".claude/agents/trellis-reviewer.md",
            ".claude/commands/open-trellis.md",
            ".claude/skills/trellis-flow/SKILL.md",
            ".agents/skills/my-trellis-helper/SKILL.md",
            ".codex/agents/trellis-worker.md",
            ".codex/hooks/session-start.py",
            ".codex/hooks/inject-workflow-state.py",
            ".codex/hooks/inject-subagent-context.py",
            ".dsh/skills/trellis-runtime/SKILL.md",
            ".claude/settings.json",
            ".codex/hooks.json",
            ".codex/config.toml",
        )
        platform_payloads = {
            relative: (self.root / relative).read_bytes() for relative in platform_sources
        }
        unknown = {
            relative: (self.root / relative).read_bytes()
            for relative in (
                "src/keep.py",
                ".claude/hooks/custom.py",
                ".claude/commands/custom.md",
                "docs/decisions.md",
            )
        }

        self.apply_fixture()

        for relative, payload in trellis_payloads.items():
            self.assertEqual(
                (self.root / "docs/archive/trellis/.trellis" / relative).read_bytes(),
                payload,
                relative,
            )
        for relative, payload in platform_payloads.items():
            archived = self.root / "docs/archive/trellis/platform" / relative
            self.assertEqual(archived.read_bytes(), payload, relative)
        for relative in platform_sources[:-3]:
            self.assertFalse((self.root / relative).exists(), relative)
        for relative, payload in unknown.items():
            self.assertEqual((self.root / relative).read_bytes(), payload, relative)
        self.assertTrue((self.root / ".codex/hooks").is_symlink())
        self.assertEqual(os.readlink(self.root / ".codex/hooks"), "../.claude/hooks")

    def test_apply_rewrites_only_the_contract_parts_of_configs_and_rule_files(self):
        self.apply_fixture()

        claude = json.loads((self.root / ".claude/settings.json").read_text())
        codex = json.loads((self.root / ".codex/hooks.json").read_text())
        self.assertEqual(claude["env"], {"KEEP_ME": "yes"})
        self.assertEqual(claude["enabledPlugins"], {"fixture@example": True})
        self.assertEqual(claude["unrelated"], [1, 2, 3])
        self.assertNotIn("LegacyOnly", claude["hooks"])
        self.assertEqual(claude["hooks"]["Notification"][0]["hooks"][0]["command"], "python3 notify.py")
        custom_group = next(
            group
            for group in claude["hooks"]["SessionStart"]
            if any(h.get("command") == "python3 .claude/hooks/custom.py" for h in group["hooks"])
        )
        self.assertEqual(custom_group["matcher"], "startup")
        self.assertEqual(custom_group["groupMeta"], "keep")
        self.assertEqual(codex["keep"], {"nested": True})
        self.assertIn("python3 keep-stop.py", hook_commands(codex))
        for data in (claude, codex):
            commands = hook_commands(data)
            for old_name in LEGACY_HOOKS:
                self.assertFalse(any(old_name in command for command in commands), commands)
        self.assertEqual(
            sum(command.endswith("/.claude/hooks/session_start.py") for command in hook_commands(claude)),
            1,
        )
        self.assertEqual(
            sum(command == "python3 .codex/hooks/stop_guard.py" for command in hook_commands(codex)),
            1,
        )

        toml = (self.root / ".codex/config.toml").read_text()
        self.assertNotIn("# Generated by Trellis", toml)
        self.assertNotIn("# treLLis compatibility comment", toml)
        self.assertIn('project_doc_fallback_filenames = ["TRELLIS.md"]', toml)
        self.assertIn("[agents]", toml)
        self.assertIn("max_depth = 1", toml)

        agents = (self.root / "AGENTS.md").read_text()
        self.assertNotIn("<!-- TRELLIS:", agents)
        self.assertNotIn("Legacy Trellis injected instructions", agents)
        self.assertIn("Keep this owner rule.", agents)
        self.assertIn("Manual Trellis note points at .trellis/manual.md", agents)
        self.assertIn("Keep this owner rule.\n\nManual Trellis note", agents)
        expected_routing = template_routing_table()
        routing_heading = expected_routing.splitlines()[0]
        self.assertIn(expected_routing, agents)
        self.assertEqual(agents.splitlines().count(routing_heading), 1)
        self.assertNotIn("[示例：", agents)
        self.assertNotIn("[占位：", agents)

        self.assertEqual(
            (self.root / ".gitattributes").read_text(),
            "*.txt text\n*.bin binary\n",
        )
        gitignore = (self.root / ".gitignore").read_text()
        self.assertEqual(gitignore, "dist/\n.scratch/.session\n")
        self.assertEqual(gitignore.splitlines().count(".scratch/.session"), 1)
        self.assertTrue((self.root / "CLAUDE.md").is_symlink())
        self.assertEqual(os.readlink(self.root / "CLAUDE.md"), "AGENTS.md")
        self.assertTrue((self.root / ".scratch/.gitkeep").is_file())
        self.assertTrue((self.root / ".claude/hooks/session_start.py").is_file())
        self.assertTrue((self.root / ".claude/hooks/stop_guard.py").is_file())
        self.assertTrue((self.root / ".agents/skills/interview-me/SKILL.md").is_file())
        self.assertTrue((self.root / ".claude/skills/interview-me").is_symlink())

    def test_apply_reports_remaining_manual_trellis_references(self):
        result = self.apply_fixture()
        self.assertRegex(
            result.stdout,
            r"AGENTS\.md:\d+.*Manual Trellis note points at \.trellis/manual\.md",
        )

    def test_migrates_after_trellis_uninstall_removed_platform_files(self):
        # Model the real recovery order: uninstall removed platform artifacts and
        # all of .trellis, then the owner restored only these Trellis data trees.
        for path in (
            self.root / ".trellis/templates",
            self.root / ".trellis/agents",
            self.root / ".trellis/scripts",
            self.root / ".trellis/extras",
            self.root / ".claude/agents",
            self.root / ".claude/skills/trellis-flow",
            self.root / ".agents/skills/my-trellis-helper",
            self.root / ".codex/agents",
            self.root / ".codex/hooks",
            self.root / ".dsh/skills/trellis-runtime",
        ):
            shutil.rmtree(path)
        for path in (
            self.root / ".claude/hooks/session-start.py",
            self.root / ".claude/hooks/trellis_guard.py",
            self.root / ".claude/commands/open-trellis.md",
        ):
            path.unlink()

        old_claude = json.loads((self.root / ".claude/settings.json").read_text())
        old_codex = json.loads((self.root / ".codex/hooks.json").read_text())
        self.assertTrue((self.root / ".trellis/tasks").is_dir())
        self.assertTrue((self.root / ".trellis/spec/project.md").is_file())
        self.assertTrue((self.root / ".trellis/workspace").is_dir())
        self.assertTrue((self.root / ".trellis/workflow.md").is_file())
        self.assertTrue((self.root / ".trellis/config.yaml").is_file())
        self.assertIn("<!-- TRELLIS:START -->", (self.root / "AGENTS.md").read_text())
        self.assertIn(".trellis/", (self.root / ".gitattributes").read_text())

        result = self.run_migrate(*self.migrate_args("--apply"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        self.assertFalse((self.root / ".trellis").exists())
        self.assertEqual(
            (self.root / ".scratch/plan-next/spec.md").read_text().splitlines()[0],
            "Status: ready-for-agent",
        )
        for task in ("active-build", "active-review"):
            self.assertEqual(
                (self.root / ".scratch" / task / "spec.md").read_text().splitlines()[0],
                "Status: in-progress",
            )
        self.assertTrue(
            (self.root / "docs/archive/trellis/.trellis/spec/project.md").is_file()
        )
        self.assertTrue((self.root / ".claude/hooks/session_start.py").is_file())
        self.assertTrue((self.root / ".codex/hooks").is_symlink())

        claude = json.loads((self.root / ".claude/settings.json").read_text())
        codex = json.loads((self.root / ".codex/hooks.json").read_text())
        self.assertEqual(claude["env"], old_claude["env"])
        self.assertEqual(claude["enabledPlugins"], old_claude["enabledPlugins"])
        self.assertEqual(claude["unrelated"], old_claude["unrelated"])
        self.assertEqual(codex["keep"], old_codex["keep"])
        for data in (claude, codex):
            commands = hook_commands(data)
            for old_name in LEGACY_HOOKS:
                self.assertFalse(any(old_name in command for command in commands), commands)
        self.assertNotIn("<!-- TRELLIS:", (self.root / "AGENTS.md").read_text())
        self.assertNotIn(".trellis/", (self.root / ".gitattributes").read_text())

        stable = snapshot(self.root)
        second = self.run_migrate(*self.migrate_args("--apply"))
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(snapshot(self.root), stable)

    def test_second_dry_run_and_second_apply_are_true_noops(self):
        self.apply_fixture()
        stable = snapshot(self.root)

        dry = self.run_migrate(*self.migrate_args())
        self.assertEqual(dry.returncode, 0, dry.stdout + dry.stderr)
        self.assertEqual(snapshot(self.root), stable)

        apply = self.run_migrate(*self.migrate_args("--apply"))
        self.assertEqual(apply.returncode, 0, apply.stdout + apply.stderr)
        self.assertEqual(snapshot(self.root), stable)

    def test_equivalent_existing_claude_links_are_kept_and_remain_idempotent(self):
        for link_kind in ("dot-relative", "absolute"):
            with self.subTest(link_kind=link_kind), tempfile.TemporaryDirectory() as temp:
                target = Path(temp)
                self.assertEqual(run_python(FIXTURE, target).returncode, 0)
                link_target = (
                    "./AGENTS.md"
                    if link_kind == "dot-relative"
                    else str(target / "AGENTS.md")
                )
                (target / "CLAUDE.md").symlink_to(link_target)
                result = self.run_migrate(
                    *self.migrate_args("--apply"), root=target
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(os.readlink(target / "CLAUDE.md"), link_target)
                stable = snapshot(target)
                result = self.run_migrate(
                    *self.migrate_args("--apply"), root=target
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(snapshot(target), stable)

    def test_missing_source_is_only_accepted_for_a_recognized_migrated_project(self):
        with tempfile.TemporaryDirectory() as empty:
            before = snapshot(empty)
            result = self.run_migrate("--date", FIXED_DATE, root=empty)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(snapshot(empty), before)

        with tempfile.TemporaryDirectory() as fake:
            fake_root = Path(fake)
            (fake_root / "docs/archive/trellis").mkdir(parents=True)
            before = snapshot(fake_root)
            result = self.run_migrate("--date", FIXED_DATE, root=fake_root)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(snapshot(fake_root), before)

        self.apply_fixture()
        stable = snapshot(self.root)
        result = self.run_migrate(*self.migrate_args())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(snapshot(self.root), stable)

    def test_late_install_conflict_rejects_the_entire_plan_before_any_write(self):
        path = self.root / "docs/rules/harness.md"
        path.parent.mkdir(parents=True)
        path.write_text("owner version\n", encoding="utf-8")
        result = self.assert_rejected_without_writes(*self.migrate_args("--apply"))
        self.assertIn("docs/rules/harness.md", result.stdout)
        self.assertTrue((self.root / ".trellis/tasks/plan-next/task.json").is_file())
        self.assertFalse((self.root / ".scratch/plan-next").exists())

    def test_generated_name_and_duplicate_destinations_are_conflicts(self):
        cases = ("source-spec", "source-trellis-metadata", "identical-destination")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                target = Path(temp)
                result = run_python(FIXTURE, target)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                if case == "source-spec":
                    (target / ".trellis/tasks/plan-next/spec.md").write_text("original spec\n")
                elif case == "source-trellis-metadata":
                    (target / ".trellis/tasks/plan-next/trellis-task.json").write_text("original metadata\n")
                else:
                    duplicate = target / ".scratch/plan-next/prd.md"
                    duplicate.parent.mkdir(parents=True)
                    duplicate.write_bytes((target / ".trellis/tasks/plan-next/prd.md").read_bytes())
                before = snapshot(target)
                result = self.run_migrate(
                    *self.migrate_args("--apply"), root=target
                )
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual(snapshot(target), before)

    def test_platform_and_claude_link_conflicts_are_zero_write(self):
        cases = ("unknown-codex-hook", "regular-claude-file")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                target = Path(temp)
                self.assertEqual(run_python(FIXTURE, target).returncode, 0)
                if case == "unknown-codex-hook":
                    (target / ".codex/hooks/custom.py").write_text("# owner hook\n")
                else:
                    (target / "CLAUDE.md").write_text("owner file\n")
                before = snapshot(target)
                result = self.run_migrate(
                    *self.migrate_args("--apply"), root=target
                )
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual(snapshot(target), before)

    def test_unknown_or_malformed_task_metadata_is_never_guessed(self):
        cases = {
            "bad-json": "{broken",
            "not-object": "[]\n",
            "missing-status": '{"title": "No status"}\n',
            "unknown-status": '{"title": "Odd", "status": "paused"}\n',
        }
        for case, content in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                target = Path(temp)
                self.assertEqual(run_python(FIXTURE, target).returncode, 0)
                metadata = target / ".trellis/tasks/plan-next/task.json"
                metadata.write_text(content, encoding="utf-8")
                before = snapshot(target)
                result = self.run_migrate(
                    *self.migrate_args("--apply"), root=target
                )
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual(snapshot(target), before)
                self.assertIn("plan-next", result.stdout + result.stderr)

    def test_non_string_task_status_is_a_reported_zero_write_conflict(self):
        for status_value in ([], {}):
            with self.subTest(status=status_value), tempfile.TemporaryDirectory() as temp:
                target = Path(temp)
                self.assertEqual(run_python(FIXTURE, target).returncode, 0)
                metadata = target / ".trellis/tasks/plan-next/task.json"
                metadata.write_text(
                    json.dumps({"title": "Bad status", "status": status_value}) + "\n",
                    encoding="utf-8",
                )
                before = snapshot(target)
                result = self.run_migrate(
                    *self.migrate_args("--apply"), root=target
                )
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual(snapshot(target), before)
                self.assertIn("conflict", result.stdout.lower())
                self.assertIn(".trellis/tasks/plan-next/task.json", result.stdout)
                self.assertIn(json.dumps(status_value), result.stdout)
                self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_malformed_agents_marker_block_is_a_zero_write_conflict(self):
        cases = {
            "missing-end": "prefix\n<!-- TRELLIS:START -->\nlegacy\n",
            "missing-start": "prefix\n<!-- TRELLIS:END -->\nsuffix\n",
        }
        for case, content in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                target = Path(temp)
                self.assertEqual(run_python(FIXTURE, target).returncode, 0)
                (target / "AGENTS.md").write_text(content, encoding="utf-8")
                before = snapshot(target)
                result = self.run_migrate(
                    *self.migrate_args("--apply"), root=target
                )
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual(snapshot(target), before)
                self.assertIn("AGENTS.md", result.stdout + result.stderr)

    def test_invalid_date_and_scope_arguments_are_zero_write_errors(self):
        invalid_arguments = (
            ("--date", "2026-02-30"),
            ("--scope", "missing-equals", "--date", FIXED_DATE),
            ("--scope", "active-build=.", "--date", FIXED_DATE),
            ("--scope", "active-build=../outside", "--date", FIXED_DATE),
            ("--scope", f"active-build={self.root}/absolute", "--date", FIXED_DATE),
            (
                "--scope",
                "active-build=src/one",
                "--scope",
                "active-build=src/two",
                "--date",
                FIXED_DATE,
            ),
        )
        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments):
                before = snapshot(self.root)
                result = self.run_migrate(*arguments, "--apply")
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual(snapshot(self.root), before)

    def test_source_and_destination_symlinks_cannot_escape_the_project(self):
        cases = ("source-file", "archive-parent", "scope")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
                target = Path(temp)
                outside_root = Path(outside)
                self.assertEqual(run_python(FIXTURE, target).returncode, 0)
                sentinel = outside_root / "sentinel.txt"
                sentinel.write_text("external bytes\n")
                if case == "source-file":
                    source = target / ".trellis/tasks/plan-next/notes.txt"
                    source.unlink()
                    source.symlink_to(sentinel)
                    arguments = self.migrate_args("--apply")
                elif case == "archive-parent":
                    archive = target / "docs/archive/trellis"
                    archive.parent.mkdir(parents=True)
                    archive.symlink_to(outside_root, target_is_directory=True)
                    arguments = self.migrate_args("--apply")
                else:
                    scope = target / "scope-link"
                    scope.symlink_to(outside_root, target_is_directory=True)
                    arguments = (
                        "--scope",
                        "active-build=scope-link/",
                        "--scope",
                        "active-review=src/review/",
                        "--date",
                        FIXED_DATE,
                        "--apply",
                    )
                before = snapshot(target)
                outside_before = snapshot(outside_root)
                result = self.run_migrate(*arguments, root=target)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual(snapshot(target), before)
                self.assertEqual(snapshot(outside_root), outside_before)

    def test_external_config_symlinks_are_rejected_before_any_read_or_write(self):
        for case in ("codex-config", "claude-parent"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside, tempfile.TemporaryDirectory() as guard_temp:
                target = Path(temp)
                outside_root = Path(outside)
                guard = Path(guard_temp)
                self.assertEqual(run_python(FIXTURE, target).returncode, 0)

                external_git = outside_root / ".git"
                if case == "codex-config":
                    external = external_git / "hooks.json"
                    external.parent.mkdir(parents=True)
                    external.write_text('{"secret": "must-not-read"}\n')
                    config = target / ".codex/hooks.json"
                    config.unlink()
                    config.symlink_to(external)
                    forbidden = config
                else:
                    external = external_git / "claude/settings.json"
                    external.parent.mkdir(parents=True)
                    external.write_text('{"secret": "must-not-read"}\n')
                    shutil.rmtree(target / ".claude")
                    (target / ".claude").symlink_to(
                        external.parent, target_is_directory=True
                    )
                    forbidden = target / ".claude"

                touched = guard / "external-read-attempted"
                (guard / "sitecustomize.py").write_text(
                    "import os, sys\n"
                    "FORBIDDEN = [os.path.abspath(p) for p in "
                    "os.environ['TRELLIS_TEST_FORBIDDEN'].split(os.pathsep)]\n"
                    "TOUCHED = os.environ['TRELLIS_TEST_TOUCHED']\n"
                    "def within(path):\n"
                    "    lexical = os.path.abspath(os.fsdecode(path))\n"
                    "    resolved = os.path.realpath(lexical)\n"
                    "    return any(p == base or p.startswith(base + os.sep) "
                    "for base in FORBIDDEN for p in (lexical, resolved))\n"
                    "def audit(event, args):\n"
                    "    if event == 'open' and args and isinstance(args[0], (str, bytes)) "
                    "and within(args[0]):\n"
                    "        fd = os.open(TOUCHED, os.O_WRONLY | os.O_CREAT, 0o600)\n"
                    "        os.close(fd)\n"
                    "        raise RuntimeError('forbidden external read')\n"
                    "sys.addaudithook(audit)\n",
                    encoding="utf-8",
                )
                env = python_env(
                    PYTHONPATH=str(guard),
                    TRELLIS_TEST_FORBIDDEN=(
                        str(forbidden) + os.pathsep + str(external_git)
                    ),
                    TRELLIS_TEST_TOUCHED=str(touched),
                )
                target_before = snapshot(target)
                outside_before = snapshot(outside_root)
                for mode in ((), ("--apply",)):
                    result = self.run_migrate(
                        *self.migrate_args(*mode), root=target, env=env
                    )
                    self.assertEqual(
                        result.returncode, 1, result.stdout + result.stderr
                    )
                    self.assertNotIn("Traceback", result.stdout + result.stderr)
                    self.assertFalse(touched.exists(), "external symlink was opened")
                    self.assertEqual(snapshot(target), target_before)
                    self.assertEqual(snapshot(outside_root), outside_before)

    def test_migration_neither_traverses_dot_git_nor_executes_git(self):
        git_dir = self.root / ".git"
        git_dir.mkdir()
        (git_dir / "private").write_text("must not be read\n")
        with tempfile.TemporaryDirectory() as guard_temp:
            guard = Path(guard_temp)
            touched = guard / "violation"
            sitecustomize = guard / "sitecustomize.py"
            sitecustomize.write_text(
                "import os\n"
                "GUARD = os.path.abspath(os.environ['TRELLIS_TEST_GIT_DIR'])\n"
                "TOUCHED = os.environ['TRELLIS_TEST_TOUCHED']\n"
                "def mark():\n"
                "    fd = os.open(TOUCHED, os.O_WRONLY | os.O_CREAT, 0o600)\n"
                "    os.close(fd)\n"
                "def guarded(function):\n"
                "    def call(path, *args, **kwargs):\n"
                "        if isinstance(path, (str, bytes)):\n"
                "            absolute = os.path.abspath(os.fsdecode(path))\n"
                "            if absolute == GUARD or absolute.startswith(GUARD + os.sep):\n"
                "                mark()\n"
                "                raise RuntimeError('forbidden .git metadata access')\n"
                "        return function(path, *args, **kwargs)\n"
                "    return call\n"
                "os.stat = guarded(os.stat)\n"
                "os.lstat = guarded(os.lstat)\n"
                "def audit(event, args):\n"
                "    if event in ('open', 'os.listdir', 'os.scandir') and args:\n"
                "        raw = args[0]\n"
                "        if isinstance(raw, (str, bytes)):\n"
                "            path = os.path.abspath(os.fsdecode(raw))\n"
                "            if path == GUARD or path.startswith(GUARD + os.sep):\n"
                "                mark()\n"
                "                raise RuntimeError('forbidden .git access')\n"
                "    if event == 'subprocess.Popen':\n"
                "        command = args[1] if len(args) > 1 else args[0]\n"
                "        words = command if isinstance(command, (list, tuple)) else [command]\n"
                "        if words and os.path.basename(os.fsdecode(words[0])) == 'git':\n"
                "            mark()\n"
                "            raise RuntimeError('forbidden git execution')\n"
                "    if event == 'os.system' and args and b'git' in args[0].lower():\n"
                "        mark()\n"
                "        raise RuntimeError('forbidden git execution')\n"
                "import sys\n"
                "sys.addaudithook(audit)\n",
                encoding="utf-8",
            )
            env = python_env(
                PYTHONPATH=str(guard),
                TRELLIS_TEST_GIT_DIR=str(git_dir),
                TRELLIS_TEST_TOUCHED=str(touched),
            )
            result = self.run_migrate(*self.migrate_args(), env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(touched.exists(), "migration accessed .git or executed git")
            self.assertEqual((git_dir / "private").read_text(), "must not be read\n")


if __name__ == "__main__":
    unittest.main()
