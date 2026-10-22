import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hook_support import STOP_GUARD, HookCase


class HookBlackBoxTest(HookCase):
    def test_stop_guard_no_root_no_task_ready_and_missing_transcript_are_silent(self):
        with self.subTest("no scratch root"):
            self.reset_root()
            scratch = self.root / ".scratch"
            scratch.rmdir()
            self.assertEqual(self.run_stop(), "")

        with self.subTest("no task"):
            self.reset_root()
            code = self.root / "changed.py"
            code.write_text("x", encoding="utf-8")
            self.transcript(
                *self.claude_call(
                    "Edit",
                    {"file_path": str(code)},
                    1_900_000_000_000_000_200,
                    1_900_000_000_000_000_400,
                )
            )
            self.assertEqual(self.run_stop(), "")

        with self.subTest("ready task"):
            self.reset_root()
            _, _, code, base = self.stop_fixture(status="ready-for-agent")
            self.transcript(
                *self.claude_call(
                    "Edit", {"file_path": str(code)}, base + 200, base + 400
                )
            )
            self.assertEqual(self.run_stop(), "")

        with self.subTest("missing transcript"):
            self.reset_root()
            self.stop_fixture()
            self.assertEqual(self.run_stop(), "")

    def test_stop_guard_each_condition_and_strict_mtime_edges(self):
        with self.subTest("two active tasks"):
            self.reset_root()
            transcript, _, _, _ = self.named_edit()
            self.make_task("second")
            self.assertEqual(self.run_stop(), "")

        with self.subTest("latest mtime equals spec"):
            self.reset_root()
            transcript, spec, code, base = self.named_edit()
            self.set_mtime(spec, base + 300)
            self.set_mtime(code, base + 300)
            self.assertEqual(code.stat().st_mtime_ns, spec.stat().st_mtime_ns)
            self.assertEqual(self.run_stop(), "")

        with self.subTest("latest mtime is earlier than spec"):
            self.reset_root()
            transcript, spec, code, base = self.named_edit()
            self.set_mtime(spec, base + 400)
            self.set_mtime(code, base + 300)
            self.assertLess(code.stat().st_mtime_ns, spec.stat().st_mtime_ns)
            self.assertEqual(self.run_stop(), "")

        with self.subTest("stop hook already active"):
            self.reset_root()
            transcript, _, _, _ = self.named_edit()
            self.assertEqual(
                self.run_stop(self.stop_payload(transcript, stop_hook_active=True)), ""
            )

    def test_stop_guard_all_conditions_block_with_task_name(self):
        self.named_edit()
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
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                self.assertEqual(result.stdout, "")

        self.named_edit()
        for payload in (
            self.stop_payload(cwd=3),
            self.stop_payload(cwd=[]),
            self.stop_payload(stop_hook_active="false"),
            self.stop_payload(stop_hook_active=0),
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.run_stop(payload), "")

        spec = self.root / ".scratch" / "active" / "spec.md"
        spec.unlink()
        spec.mkdir()
        self.assertEqual(self.run_stop(), "")

    def test_stop_guard_scoped_single_ignores_outside_changes(self):
        _, spec = self.make_task("scoped", scope="service/")
        scope = self.root / "service"
        scope.mkdir()
        outside = self.root / "other" / "changed.py"
        outside.parent.mkdir()
        outside.write_text("changed = True\n", encoding="utf-8")
        base = 1_900_000_000_000_000_000
        self.set_mtime(spec, base + 100)
        self.set_mtime(outside, base + 300)
        self.transcript(
            *self.claude_call(
                "Edit", {"file_path": str(outside)}, base + 200, base + 400
            )
        )
        self.assertEqual(self.run_stop(), "")

        inside = scope / "changed.py"
        inside.write_text("changed = True\n", encoding="utf-8")
        self.set_mtime(inside, base + 300)
        self.transcript(
            *self.claude_call(
                "Edit", {"file_path": str(inside)}, base + 200, base + 400
            )
        )
        self.assert_block(self.run_stop(), "scoped")

    def test_stop_guard_selects_scoped_task_from_multiple(self):
        _, api_spec = self.make_task("api", scope="services/api/")
        _, web_spec = self.make_task("web", scope="services/web/")
        _, legacy_spec = self.make_task("legacy")
        api = self.root / "services" / "api"
        web = self.root / "services" / "web"
        api.mkdir(parents=True)
        web.mkdir()
        changed = api / "changed.py"
        changed.write_text("changed = True\n", encoding="utf-8")
        base = 1_900_000_000_000_000_000
        for path in (api_spec, web_spec, legacy_spec):
            self.set_mtime(path, base + 100)
        self.set_mtime(changed, base + 300)
        transcript = self.transcript(
            *self.claude_call(
                "Edit", {"file_path": str(changed)}, base + 200, base + 400
            )
        )
        self.assert_block(
            self.run_stop(
                {
                    "cwd": str(api),
                    "stop_hook_active": False,
                    "transcript_path": str(transcript),
                }
            ),
            "api",
        )
        self.assertEqual(self.run_stop(self.stop_payload(transcript)), "")

        _, inner_spec = self.make_task("inner", scope="services/api/handlers/")
        handlers = api / "handlers"
        handlers.mkdir()
        self.set_mtime(inner_spec, base + 100)
        self.assertEqual(
            self.run_stop(
                {
                    "cwd": str(handlers),
                    "stop_hook_active": False,
                    "transcript_path": str(transcript),
                }
            ),
            "",
        )

    def test_stop_guard_scoped_excluded_directory_remains_excluded(self):
        _, spec = self.make_task("config", scope=".claude/work/")
        changed = self.root / ".claude" / "work" / "changed.py"
        changed.parent.mkdir(parents=True)
        changed.write_text("changed = True\n", encoding="utf-8")
        base = 1_900_000_000_000_000_000
        self.set_mtime(spec, base + 100)
        self.set_mtime(changed, base + 300)
        self.transcript(
            *self.claude_call(
                "Edit", {"file_path": str(changed)}, base + 200, base + 400
            )
        )
        self.assertEqual(self.run_stop(), "")

    def test_invalid_scopes_fail_open_for_both_hooks(self):
        def assert_invalid(scope, changed):
            _, spec = self.make_task("invalid", scope=scope)
            changed.parent.mkdir(parents=True, exist_ok=True)
            changed.write_text("changed = True\n", encoding="utf-8")
            base = 1_900_000_000_000_000_000
            self.set_mtime(spec, base + 100)
            self.set_mtime(changed, base + 300)
            transcript = self.transcript(
                *self.claude_call(
                    "Edit", {"file_path": str(changed)}, base + 200, base + 400
                )
            )
            payload = {"cwd": str(self.root), "source": "resume"}
            self.assertEqual(self.run_session(payload), "")
            payload["stop_hook_active"] = False
            payload["transcript_path"] = str(transcript)
            self.assertEqual(self.run_stop(payload), "")

        with self.subTest(scope="empty"):
            assert_invalid("", self.root / "changed.py")

        for kind in ("traversal", "absolute", "symlink"):
            with (
                self.subTest(scope=kind),
                tempfile.TemporaryDirectory(dir=self.root.parent) as outside,
            ):
                self.reset_root()
                outside = Path(outside)
                changed = outside / "changed.py"
                if kind == "traversal":
                    scope = f"../{outside.name}/"
                elif kind == "absolute":
                    scope = f"{outside}/"
                else:
                    (self.root / "escape").symlink_to(outside, target_is_directory=True)
                    scope = "escape/"
                assert_invalid(scope, changed)

    def test_stop_guard_bad_spec_skips_only_that_task(self):
        self.named_edit()
        broken = self.root / ".scratch" / "broken"
        broken.mkdir()
        (broken / "spec.md").symlink_to("missing.md")
        self.assert_block(self.run_stop(), "active")

        self.reset_root()
        self.named_edit()
        invalid = self.root / ".scratch" / "invalid"
        invalid.mkdir()
        (invalid / "spec.md").write_bytes(b"Status: in-progress\n\xff")
        self.assert_block(self.run_stop(), "active")

    def test_stop_guard_excludes_named_directories_at_any_depth(self):
        transcript, spec, allowed, base = self.named_edit()
        excluded = (
            ".scratch",
            ".git",
            ".claude",
            ".codex",
            "node_modules",
            ".venv",
            "venv",
            "__pycache__",
            "dist",
            "build",
            ".next",
            "target",
        )
        rows = []
        for name in excluded:
            path = self.root / "nested" / name / "deeper" / "ignored.txt"
            path.parent.mkdir(parents=True)
            path.write_text("ignored\n", encoding="utf-8")
            self.set_mtime(path, 1_900_000_000_000_000_500)
            rows.extend(
                self.claude_call(
                    "Edit",
                    {"file_path": str(path)},
                    base + 200,
                    base + 600,
                    call_id=f"excluded-{name}",
                )
            )
        self.transcript(*rows)
        self.set_mtime(allowed, base + 100)
        self.assertEqual(self.run_stop(), "")

    def test_stop_guard_20000_files_allowed_and_20001_files_pass_through(self):
        _, spec, code, _ = self.named_edit()
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
        self.set_mtime(spec, base + 100)
        self.set_mtime(first, base + 300)
        self.transcript(
            *self.claude_call(
                "Edit", {"file_path": str(first)}, base + 200, base + 400
            ),
            mtime=base + 500,
        )
        self.assert_block(self.run_stop(), "active")

        extra = fill / "20000.txt"
        extra.write_text("x", encoding="utf-8")
        self.set_mtime(extra, base + 300)
        self.assertEqual(self.run_stop(), "")

    def test_readonly_bash_window_and_other_session_edit_do_not_count(self):
        _, spec, code, base = self.stop_fixture()
        reader = self.transcript(
            *self.claude_call(
                "Bash", {"command": "python3 -m pytest tests"}, base + 200, base + 400
            )
        )
        self.transcript(
            *self.claude_call("Edit", {"file_path": str(code)}, base + 200, base + 400),
            path=self.root / ".claude" / "other-session.jsonl",
        )
        self.assertLess(base + 200, code.stat().st_mtime_ns)
        self.assertLess(code.stat().st_mtime_ns, base + 400)
        self.assertEqual(self.run_stop(self.stop_payload(reader)), "")

    def test_direct_edit_tools_block_even_outside_command_windows(self):
        for tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
            with self.subTest(tool=tool):
                self.reset_root()
                _, spec, code, base = self.stop_fixture()
                field = "notebook_path" if tool == "NotebookEdit" else "file_path"
                if tool == "NotebookEdit":
                    code = self.root / "src" / "note.ipynb"
                    code.write_text("{}", encoding="utf-8")
                self.set_mtime(code, base + 5_000_000)
                self.transcript(
                    *self.claude_call(tool, {field: str(code)}, base + 200, base + 400)
                )
                self.assert_block(self.run_stop(), "active")

    def test_direct_edit_failure_old_result_and_other_path_release(self):
        for kind in (
            "is_error",
            "result_equal_spec",
            "result_before_spec",
            "different_path",
        ):
            with self.subTest(kind=kind):
                self.reset_root()
                _, spec, code, base = self.stop_fixture()
                other = self.root / "elsewhere" / "changed.py"
                rows = self.claude_call(
                    "Edit",
                    {"file_path": str(other if kind == "different_path" else code)},
                    base,
                    base
                    + (
                        100
                        if kind == "result_equal_spec"
                        else 99
                        if kind == "result_before_spec"
                        else 400
                    ),
                    error=(kind == "is_error"),
                )
                self.transcript(*rows)
                self.assertEqual(self.run_stop(), "")

    def test_command_name_window_heredoc_and_prefix_mismatch(self):
        _, spec, unused, base = self.stop_fixture()
        code = self.root / "tests" / "x.mjs"
        code.parent.mkdir()
        code.write_text("x", encoding="utf-8")
        self.set_mtime(code, base + 300)
        command = "cat >> tests/x.mjs <<'EOF'\nx\nEOF"
        self.transcript(
            *self.claude_call("Bash", {"command": command}, base + 200, base + 400)
        )
        self.assert_block(self.run_stop(), "active")
        self.set_mtime(code, base + 1_000_401)
        self.assertEqual(self.run_stop(), "")

        self.reset_root()
        _, _, unused, base = self.stop_fixture()
        app = self.root / "app.py"
        app.write_text("x", encoding="utf-8")
        self.set_mtime(app, base + 300)
        self.transcript(
            *self.claude_call(
                "Bash", {"command": "cat > myapp.py"}, base + 200, base + 400
            )
        )
        self.assertEqual(self.run_stop(), "")

    def test_command_window_right_boundary_is_inclusive_one_millisecond(self):
        _, spec, code, base = self.stop_fixture()
        end = base + 2_000_000
        self.transcript(
            *self.claude_call("Bash", {"command": "cat > changed.py"}, base + 200, end)
        )
        self.set_mtime(code, end + 1_000_000)
        self.assert_block(self.run_stop(), "active")
        self.set_mtime(code, end + 1_000_001)
        self.assertEqual(self.run_stop(), "")

    def test_git_worktree_commands_count_but_status_does_not(self):
        for command, blocked in (
            ("git merge feat", True),
            ("git -C /x merge feat", True),
            ('git -C "/tmp/work tree" merge feat', True),
            ("git -c user.name=abc --no-pager restore .", True),
            ("git status", False),
            ("git merge-base main HEAD", False),
            ("git -C /x; merge feat", False),
            ("git -c key=value; merge feat", False),
        ):
            with self.subTest(command=command):
                self.reset_root()
                _, _, code, base = self.stop_fixture()
                self.transcript(
                    *self.claude_call(
                        "Bash", {"command": command}, base + 200, base + 400
                    )
                )
                output = self.run_stop()
                if blocked:
                    self.assert_block(output, "active")
                else:
                    self.assertEqual(output, "")

    def test_recursive_subagent_history_is_evidence_but_external_path_is_not(self):
        for relative in ("agent-1.jsonl", "workflows/wf_1/agent-2.jsonl"):
            with self.subTest(relative=relative):
                self.reset_root()
                _, _, code, base = self.stop_fixture()
                main = self.transcript()
                child = main.with_suffix("") / "subagents" / relative
                self.transcript(
                    *self.claude_call(
                        "Edit", {"file_path": str(code)}, base + 200, base + 400
                    ),
                    path=child,
                )
                self.assert_block(self.run_stop(self.stop_payload(main)), "active")

        self.reset_root()
        _, _, code, base = self.stop_fixture()
        with tempfile.TemporaryDirectory(dir=self.root.parent) as outside:
            external = Path(outside) / "changed.py"
            main = self.transcript()
            child = main.with_suffix("") / "subagents" / "agent-outside.jsonl"
            self.transcript(
                *self.claude_call(
                    "Edit", {"file_path": str(external)}, base + 200, base + 400
                ),
                path=child,
            )
            self.assertEqual(self.run_stop(self.stop_payload(main)), "")

    def test_codex_file_change_completed_time_int_and_string(self):
        for as_string in (False, True):
            with self.subTest(as_string=as_string):
                self.reset_root()
                _, _, code, base = self.stop_fixture()
                completed = (base + 2_000_000) // 1_000_000
                self.transcript(
                    {
                        "type": "event_msg",
                        "timestamp": self.stamp(base + 2_000_000),
                        "payload": {
                            "type": "item_completed",
                            "completed_at_ms": str(completed)
                            if as_string
                            else completed,
                            "item": {
                                "type": "FileChange",
                                "changes": {str(code): {"type": "update"}},
                            },
                        },
                    }
                )
                self.assert_block(self.run_stop(), "active")

    def test_codex_file_change_requires_new_completion_and_same_path(self):
        for kind in ("old", "other"):
            with self.subTest(kind=kind):
                self.reset_root()
                _, _, code, base = self.stop_fixture()
                path = str(
                    code if kind == "old" else self.root / "other" / "changed.py"
                )
                completed = (base if kind == "old" else base + 2_000_000) // 1_000_000
                self.transcript(
                    {
                        "type": "event_msg",
                        "timestamp": self.stamp(base + 2_000_000),
                        "payload": {
                            "type": "item_completed",
                            "completed_at_ms": completed,
                            "item": {"type": "FileChange", "changes": {path: {}}},
                        },
                    }
                )
                self.assertEqual(self.run_stop(), "")

    def test_codex_exec_js_input_names_file_in_window(self):
        _, _, unused, base = self.stop_fixture()
        out = self.root / "out.txt"
        out.write_text("x", encoding="utf-8")
        self.set_mtime(out, base + 3_000_000)
        self.transcript(
            {
                "type": "response_item",
                "timestamp": self.stamp(base + 2_000_000),
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "js-1",
                    "name": "exec",
                    "input": 'await tools.exec_command({cmd:"cat > out.txt"})',
                },
            },
            {
                "type": "response_item",
                "timestamp": self.stamp(base + 4_000_000),
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "js-1",
                    "output": "done",
                },
            },
        )
        self.assert_block(self.run_stop(), "active")

    def test_codex_last_output_extends_window(self):
        _, _, code, base = self.stop_fixture()
        self.set_mtime(code, base + 5_000_000)
        self.transcript(
            {
                "type": "response_item",
                "timestamp": self.stamp(base + 2_000_000),
                "payload": {
                    "type": "function_call",
                    "call_id": "same",
                    "name": "exec_command",
                    "arguments": json.dumps({"cmd": "cat > changed.py"}),
                },
            },
            {
                "type": "response_item",
                "timestamp": self.stamp(base + 3_000_000),
                "payload": {
                    "type": "function_call_output",
                    "call_id": "same",
                    "output": "first",
                },
            },
            {
                "type": "response_item",
                "timestamp": self.stamp(base + 6_000_000),
                "payload": {
                    "type": "function_call_output",
                    "call_id": "same",
                    "output": "last",
                },
            },
        )
        self.assert_block(self.run_stop(), "active")

    def test_codex_function_call_escaped_quotes_and_shell_action(self):
        for kind in ("escaped", "shell_action"):
            with self.subTest(kind=kind):
                self.reset_root()
                _, _, code, base = self.stop_fixture()
                if kind == "escaped":
                    call = {
                        "type": "response_item",
                        "timestamp": self.stamp(base + 200),
                        "payload": {
                            "type": "function_call",
                            "call_id": "c",
                            "name": "exec_command",
                            "arguments": json.dumps({"cmd": 'cat > "changed.py"'}),
                        },
                    }
                else:
                    call = {
                        "type": "response_item",
                        "timestamp": self.stamp(base + 200),
                        "payload": {
                            "type": "local_shell_call",
                            "call_id": "c",
                            "action": {"command": ["sh", "-c", "cat > changed.py"]},
                        },
                    }
                output = {
                    "type": "response_item",
                    "timestamp": self.stamp(base + 400),
                    "payload": {
                        "type": "function_call_output",
                        "call_id": "c",
                        "output": "done",
                    },
                }
                self.transcript(call, output)
                self.assert_block(self.run_stop(), "active")

    def test_each_codex_command_tool_name_accepts_raw_input(self):
        for name in (
            "exec",
            "exec_command",
            "shell",
            "local_shell_call",
            "write_stdin",
            "js",
        ):
            with self.subTest(name=name):
                self.reset_root()
                _, _, code, base = self.stop_fixture()
                self.transcript(
                    {
                        "type": "response_item",
                        "timestamp": self.stamp(base + 200),
                        "payload": {
                            "type": "custom_tool_call",
                            "call_id": "c",
                            "name": name,
                            "input": "cat > changed.py",
                        },
                    },
                    {
                        "type": "response_item",
                        "timestamp": self.stamp(base + 400),
                        "payload": {
                            "type": "custom_tool_call_output",
                            "call_id": "c",
                            "output": "done",
                        },
                    },
                )
                self.assert_block(self.run_stop(), "active")

    def test_noncommand_tools_and_unpaired_bash_are_not_evidence(self):
        for tool in ("AskUserQuestion", "Agent", "Bash"):
            with self.subTest(tool=tool):
                self.reset_root()
                _, _, code, base = self.stop_fixture()
                call = self.claude_call(
                    tool,
                    {"command": "cat > changed.py", "prompt": "changed.py"},
                    base + 200,
                    base + 400,
                )
                self.transcript(*(call[:1] if tool == "Bash" else call))
                self.assertEqual(self.run_stop(), "")

    def test_transcript_path_must_be_existing_regular_file(self):
        _, _, code, base = self.stop_fixture()
        directory = self.root / "a-directory"
        directory.mkdir()
        cases = (None, "", 1, [], str(self.root / "missing.jsonl"), str(directory))
        for value in cases:
            with self.subTest(value=value):
                payload = {
                    "cwd": str(self.root),
                    "stop_hook_active": False,
                    "transcript_path": value,
                }
                self.assertEqual(self.run_stop(payload), "")
        payload.pop("transcript_path")
        self.assertEqual(self.run_stop(payload), "")

    def test_missing_stop_hook_active_defaults_to_false(self):
        _, _, code, base = self.stop_fixture()
        transcript = self.transcript(
            *self.claude_call("Edit", {"file_path": str(code)}, base + 200, base + 400)
        )
        self.assert_block(
            self.run_stop({"cwd": str(self.root), "transcript_path": str(transcript)}),
            "active",
        )

    def test_old_transcript_and_subagent_file_are_skipped_whole(self):
        _, spec, code, base = self.stop_fixture()
        edit = self.claude_call(
            "Edit", {"file_path": str(code)}, base + 200, base + 400
        )
        main = self.transcript(*edit, mtime=base + 100)
        self.assertEqual(self.run_stop(self.stop_payload(main)), "")
        main = self.transcript(mtime=base + 500)
        child = main.with_suffix("") / "subagents" / "agent.jsonl"
        self.transcript(*edit, path=child, mtime=base + 100)
        self.assertEqual(self.run_stop(self.stop_payload(main)), "")
        self.set_mtime(child, base + 500)
        self.assert_block(self.run_stop(self.stop_payload(main)), "active")

    def test_bad_json_half_line_and_bad_timestamp_do_not_hide_good_evidence(self):
        _, _, code, base = self.stop_fixture()
        good = self.claude_call(
            "Edit", {"file_path": str(code)}, base + 200, base + 400
        )
        malformed = {
            "type": "assistant",
            "timestamp": "not-a-date",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "bad",
                        "name": "Edit",
                        "input": {"file_path": str(code)},
                    }
                ]
            },
        }
        self.transcript(
            '{"tool_use":',
            malformed,
            good[0],
            '{"tool_result":{"tool_use_id":',
            good[1],
        )
        self.assert_block(self.run_stop(), "active")

    def test_nine_digit_fraction_and_positive_offset_are_precise(self):
        _, _, code, base = self.stop_fixture()
        start = base + 200
        end = base + 400
        self.set_mtime(code, end + 1_000_000)
        call, result = self.claude_call(
            "Bash", {"command": "cat > changed.py"}, start, end
        )
        call["timestamp"] = self.stamp(start, offset=11)
        result["timestamp"] = self.stamp(end, offset=11)
        self.transcript(call, result)
        self.assert_block(self.run_stop(), "active")
        self.set_mtime(code, end + 1_000_001)
        self.assertEqual(self.run_stop(), "")

    def test_absent_marker_and_deleted_marker_do_not_affect_decision(self):
        _, _, code, base = self.stop_fixture()
        marker = self.root / ".scratch" / ".session"
        self.transcript(
            *self.claude_call("Write", {"file_path": str(code)}, base + 200, base + 400)
        )
        self.assertFalse(marker.exists())
        self.assert_block(self.run_stop(), "active")
        marker.write_text("legacy", encoding="utf-8")
        marker.unlink()
        self.assert_block(self.run_stop(), "active")


if __name__ == "__main__":
    unittest.main()
