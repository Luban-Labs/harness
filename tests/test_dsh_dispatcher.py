"""Offline dispatch contracts; HOME and every command are synthetic."""
import importlib.util
import json
import os
import hashlib
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

try:
    from compression import zstd
except ImportError:
    zstd = None

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "dsh" / "cc_hooks.py"
MODULE = importlib.util.spec_from_file_location("cc_dispatch", SCRIPT)
cc = importlib.util.module_from_spec(MODULE)
if SCRIPT.exists():
    MODULE.loader.exec_module(cc)


@unittest.skipIf(zstd is None, "compressed DSH dispatch needs Python 3.14")
class DispatcherTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.home = self.base / "home"
        self.root = self.base / "project"
        self.root.mkdir()
        (self.root / ".git").mkdir()
        self.sid = "session-11111111-2222-4333-8444-555555555555"
        self.log = self.home / ".dsh/sessions/bucket" / self.sid / "session.v4.jsonl.zstd"
        self.rows = [{"type": "session", "version": 4, "id": self.sid,
                      "cwd": str(self.root), "parentSession": None},
                     {"type": "turn/start", "seq": 1, "time": 1900000000000,
                      "data": {"turn": 1}}]
        self.write_log()
        self.save(self.home / ".claude.json", {"projects": {str(self.root): {"hasTrustDialogAccepted": True}}})

    def save(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def write_log(self):
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.log.write_bytes(zstd.compress(("\n".join(map(json.dumps, self.rows)) + "\n").encode()))

    def hook(self, code, **kw):
        return {"type": "command", "command": shlex.quote(sys.executable) + " -c " + shlex.quote(code), **kw}

    def settings(self, event, hooks, *, matcher=None, global_=False):
        path = self.home / ".claude/settings.json" if global_ else self.root / ".claude/settings.json"
        self.save(path, {"hooks": {event: [{"hooks": hooks, **({"matcher": matcher} if matcher else {})}]}})

    def run_dispatch(self, event, **extra):
        payload = {"hook_event_name": event, "session_id": self.sid, "cwd": str(self.root),
                   "transcript_path": "", **extra}
        out = subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps(payload),
                             capture_output=True, text=True, env={**os.environ, "HOME": str(self.home),
                             "PYTHONDONTWRITEBYTECODE": "1"}, timeout=5)
        self.assertEqual((out.returncode, out.stderr), (0, ""))
        return json.loads(out.stdout) if out.stdout else None

    def test_plain_session_stdout_becomes_context_and_settings_reload(self):
        self.settings("SessionStart", [self.hook("print('first')")])
        self.assertEqual(self.run_dispatch("SessionStart", source="startup"),
                         {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "first"}})
        self.settings("SessionStart", [self.hook("print('changed')")])
        self.assertIn("changed", str(self.run_dispatch("SessionStart", source="startup")))

    def test_created_cwd_survives_current_directory_change(self):
        self.settings("SessionStart", [self.hook("import os; print(os.environ['CLAUDE_PROJECT_DIR'])")])
        outside = self.base / "elsewhere"
        outside.mkdir()
        self.assertIn(str(self.root), str(self.run_dispatch("SessionStart", cwd=str(outside))))

    def test_untrusted_project_cannot_override_global_hooks(self):
        self.save(self.home / ".claude.json", {"projects": {str(self.root): {"hasTrustDialogAccepted": "true"}}})
        self.settings("SessionStart", [self.hook("print('PROJECT')")])
        self.settings("SessionStart", [self.hook("print('GLOBAL')")], global_=True)
        output = str(self.run_dispatch("SessionStart"))
        self.assertIn("GLOBAL", output)
        self.assertNotIn("PROJECT", output)

    def test_tool_translation_precedes_cc_matcher_and_payload(self):
        capture = "import json,os,sys; p=json.load(sys.stdin); print(json.dumps({'hookSpecificOutput': {'hookEventName':'PreToolUse','permissionDecision':'deny','permissionDecisionReason':json.dumps([p['tool_name'],p['tool_input'],os.environ['HARNESS_HOST'],p['transcript_path']])}}))"
        self.settings("PreToolUse", [self.hook(capture)], matcher="Edit|Write")
        output = self.run_dispatch("PreToolUse", tool_name="edit", tool_input={"file_path": "a.py", "old_string": "a", "new_string": "b"})
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn('"Edit"', output["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIsNone(self.run_dispatch("PreToolUse", tool_name="bash", tool_input={"command": "true"}))

    def test_extended_tool_names_map_and_unknown_names_survive(self):
        capture = "import json,sys; p=json.load(sys.stdin); print(json.dumps({'hookSpecificOutput':{'hookEventName':'PostToolUse','additionalContext':json.dumps([p['tool_name'],p['tool_input']])}}))"
        self.settings("PostToolUse", [self.hook(capture)])
        cases = {"subagent": "Agent", "subagent_fork": "Agent", "workflow": "Workflow",
                 "todo_write": "TodoWrite", "web_search": "WebSearch", "web_fetch": "WebFetch",
                 "working_directory": "working_directory", "mcp__custom__tool": "mcp__custom__tool"}
        for source, expected in cases.items():
            with self.subTest(tool=source):
                inputs = {"prompt": "question", "queries": ["first", "second"]}
                output = self.run_dispatch("PostToolUse", tool_name=source, tool_input=inputs)
                name, forwarded = json.loads(output["hookSpecificOutput"]["additionalContext"])
                self.assertEqual(name, expected)
                self.assertEqual(forwarded, inputs)
                self.assertNotIn("subagent_type", forwarded)

    def test_stop_hard_cap_survives_steer_pre_step_and_resets_next_turn(self):
        self.settings("Stop", [self.hook("import json; print(json.dumps({'decision':'block','reason':'again'}))")])
        self.run_dispatch("UserPromptSubmit", prompt="user")
        self.assertEqual(self.run_dispatch("Stop")["decision"], "block")
        self.run_dispatch("UserPromptSubmit", prompt="again")
        self.assertIsNone(self.run_dispatch("Stop"))
        self.rows.append({"type": "turn/start", "seq": 20, "time": 1900000001000, "data": {"turn": 2}})
        self.write_log()
        self.run_dispatch("UserPromptSubmit", prompt="next user")
        self.assertEqual(self.run_dispatch("Stop")["decision"], "block")

    def test_stop_adopts_late_first_boundary_after_prompt(self):
        self.settings("Stop", [self.hook("print('{\"decision\":\"block\",\"reason\":\"late\"}')")])
        self.rows = self.rows[:1]
        self.write_log()
        self.run_dispatch("UserPromptSubmit", prompt="first user")
        self.assertIsNone(self.run_dispatch("Stop"))
        self.rows.append({"type": "turn/start", "seq": 1, "time": 1900000000000, "data": {"turn": 1}})
        self.write_log()
        self.assertEqual(self.run_dispatch("Stop"), {"decision": "block", "reason": "late"})
        self.run_dispatch("UserPromptSubmit", prompt="steered continuation")
        self.assertIsNone(self.run_dispatch("Stop"))

    def test_stop_adopts_late_next_boundary_without_rearming_old_turn(self):
        self.settings("Stop", [self.hook("print('{\"decision\":\"block\",\"reason\":\"next\"}')")])
        self.run_dispatch("UserPromptSubmit", prompt="first user")
        self.assertEqual(self.run_dispatch("Stop")["decision"], "block")
        self.run_dispatch("UserPromptSubmit", prompt="second user before flush")
        self.assertIsNone(self.run_dispatch("Stop"))
        self.rows.append({"type": "turn/start", "seq": 20, "time": 1900000001000, "data": {"turn": 2}})
        self.write_log()
        self.assertEqual(self.run_dispatch("Stop"), {"decision": "block", "reason": "next"})
        self.run_dispatch("UserPromptSubmit", prompt="steered continuation")
        self.assertIsNone(self.run_dispatch("Stop"))

    def test_same_stop_hooks_share_initial_flag_and_next_event_is_active(self):
        observed = self.home / "observed.json"
        self.settings("Stop", [self.hook("print('{\"decision\":\"block\",\"reason\":\"first\"}')"),
                               self.hook("import pathlib,sys; pathlib.Path(" + repr(str(observed)) + ").write_text(sys.stdin.read())")])
        self.run_dispatch("UserPromptSubmit")
        self.run_dispatch("Stop")
        self.assertIs(json.loads(observed.read_text())["stop_hook_active"], False)
        self.assertIsNone(self.run_dispatch("Stop"))
        self.assertIs(json.loads(observed.read_text())["stop_hook_active"], True)

    def test_same_event_hooks_execute_concurrently(self):
        commands = []
        for name, peer in [("FIRST", "SECOND"), ("SECOND", "FIRST")]:
            code = ("import pathlib,time,sys; pathlib.Path(" + repr(str(self.home / name)) + ").touch(); "
                    "peer=pathlib.Path(" + repr(str(self.home / peer)) + "); "
                    "start=time.monotonic()\nwhile not peer.exists() and time.monotonic()-start<.4: time.sleep(.01)\n"
                    "sys.exit(3) if not peer.exists() else print(" + repr(name) + ")")
            commands.append(self.hook(code))
        self.settings("SessionStart", commands)
        output = self.run_dispatch("SessionStart")["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(output, "FIRST\n\nSECOND")

    def test_child_missing_agent_unknown_round_never_block(self):
        self.settings("Stop", [self.hook("import sys; sys.stderr.write('deny'); sys.exit(2)")])
        self.assertIsNone(self.run_dispatch("Stop"))
        self.assertIsNone(self.run_dispatch("Stop", session_id=""))
        self.rows[0]["parentSession"] = "parent-session"
        self.write_log()
        self.run_dispatch("UserPromptSubmit")
        self.assertIsNone(self.run_dispatch("Stop"))

    def test_other_exit_timeout_and_malformed_json_are_silent(self):
        for code, opts in [("import sys; print('{\"decision\":\"block\"}'); sys.exit(1)", {}),
                           ("import time; time.sleep(1); print('late')", {"timeout": 0.02}),
                           ("print('{broken')", {})]:
            with self.subTest(code=code):
                self.settings("PreToolUse", [self.hook(code, **opts)])
                self.assertIsNone(self.run_dispatch("PreToolUse", tool_name="bash"))

    def test_exit_two_and_json_deny_use_bridge_decisions(self):
        self.settings("PreToolUse", [self.hook("import sys; sys.stderr.write('denied'); sys.exit(2)")])
        self.assertEqual(self.run_dispatch("PreToolUse", tool_name="bash"),
                         {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "denied"}})

    def test_enabled_plugins_manifest_paths_and_override_reload(self):
        plugin = self.home / "plugin"
        self.save(plugin / ".claude-plugin/plugin.json", {"hooks": ["hooks/hooks.json", "extra.json"]})
        command = self.hook("import os; print('PLUGIN:' + os.environ['CLAUDE_PLUGIN_ROOT'])")
        self.save(plugin / "hooks/hooks.json", {"hooks": {"SessionStart": [{"hooks": [command]}]}})
        self.save(plugin / "extra.json", {"SessionStart": [{"hooks": [self.hook("print('EXTRA')")]}]})
        self.save(self.home / ".claude/plugins/installed_plugins.json", {"version": 2, "plugins": {
            "example@market": [{"scope": "user", "installPath": str(plugin)}]}})
        self.save(self.home / ".claude/settings.json", {"enabledPlugins": {"example@market": True}})
        output = self.run_dispatch("SessionStart")["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(output, "PLUGIN:" + str(plugin) + "\n\nEXTRA")
        self.save(self.root / ".claude/settings.local.json", {"enabledPlugins": {"example@market": False}})
        self.assertIsNone(self.run_dispatch("SessionStart"))
        self.save(self.home / ".claude.json", {})
        self.assertIn("PLUGIN:", str(self.run_dispatch("SessionStart")))

    def test_plugin_project_scope_does_not_run_for_another_project(self):
        plugin = self.home / "plugin"
        self.save(plugin / "hooks/hooks.json", {"SessionStart": [{"hooks": [self.hook("print('wrong-project')")]}]})
        self.save(self.home / ".claude/plugins/installed_plugins.json", {"version": 2, "plugins": {
            "x@y": [{"scope": "project", "projectPath": str(self.home), "installPath": str(plugin)}]}})
        self.save(self.home / ".claude/settings.json", {"enabledPlugins": {"x@y": True}})
        self.assertIsNone(self.run_dispatch("SessionStart"))

    def test_plugin_shell_quotes_and_exec_form_token_substitution(self):
        plugin = self.home / "plugin 'with spaces'"
        plugin.mkdir()
        (plugin / "python").symlink_to(sys.executable)
        shell_hook = {"type": "command", "command": "printf '%s|%s' '${CLAUDE_PLUGIN_ROOT}' \"${CLAUDE_PLUGIN_ROOT}\""}
        exec_hook = {"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/python", "args": [
            "-c", "import sys; print('|'.join(sys.argv[1:]))", "${CLAUDE_PLUGIN_ROOT}", "${CLAUDE_PROJECT_DIR}"]}
        self.save(plugin / "hooks/hooks.json", {"SessionStart": [{"hooks": [shell_hook, exec_hook]}]})
        self.save(self.home / ".claude/plugins/installed_plugins.json", {"version": 2, "plugins": {
            "x@y": [{"scope": "user", "installPath": str(plugin)}]}})
        self.save(self.home / ".claude/settings.json", {"enabledPlugins": {"x@y": True}})
        output = self.run_dispatch("SessionStart")["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(output, "${CLAUDE_PLUGIN_ROOT}|" + str(plugin) + "\n\n" + str(plugin) + "|" + str(self.root))

    def test_worktree_separates_settings_env_and_trust(self):
        main = self.base / "main"
        gitdir = main / ".git/worktrees/child"
        gitdir.mkdir(parents=True)
        (self.root / ".git").rmdir()
        (self.root / ".git").write_text("gitdir: " + str(gitdir))
        (gitdir / "commondir").write_text("../..")
        (gitdir / "gitdir").write_text(str(self.root / ".git"))
        self.save(self.home / ".claude.json", {"projects": {str(main): {"hasTrustDialogAccepted": True}}})
        self.settings("SessionStart", [self.hook("import os; print('WORKTREE:' + os.environ['CLAUDE_PROJECT_DIR'])")])
        self.save(main / ".claude/settings.local.json", {"hooks": {"SessionStart": [{"hooks": [self.hook("print('MAIN-LOCAL')")]}]}})
        output = str(self.run_dispatch("SessionStart"))
        self.assertIn("WORKTREE:" + str(self.root), output)
        self.assertIn("MAIN-LOCAL", output)
        context = cc.project_context(self.root, self.home)
        self.assertTrue(context["trusted"])
        self.assertEqual(context["settings_dir"], self.root)
        self.assertEqual(context["local_settings_dir"], main)
        self.save(self.home / ".claude.json", {"projects": {str(self.root): {"hasTrustDialogAccepted": True}}})
        self.assertTrue(cc.trusted_project(self.root, self.home))

    def test_creation_subdirectory_is_settings_root_not_git_root(self):
        subdir = self.root / "subdir"
        subdir.mkdir()
        self.rows[0]["cwd"] = str(subdir)
        self.write_log()
        self.settings("SessionStart", [self.hook("print('WRONG-GIT-ROOT')")])
        self.save(subdir / ".claude/settings.json", {"hooks": {"SessionStart": [{"hooks": [self.hook("print('SUBDIR')")]}]}})
        output = str(self.run_dispatch("SessionStart"))
        self.assertIn("SUBDIR", output)
        self.assertNotIn("WRONG-GIT-ROOT", output)

    def test_state_corruption_rewind_and_missing_boundary_cannot_rearm(self):
        self.settings("Stop", [self.hook("print('{\"decision\":\"block\"}')")])
        self.run_dispatch("UserPromptSubmit")
        self.assertEqual(self.run_dispatch("Stop")["decision"], "block")
        self.rows[1]["seq"] = self.rows[1]["data"]["turn"] = 0
        self.write_log()
        self.run_dispatch("UserPromptSubmit")
        self.assertIsNone(self.run_dispatch("Stop"))

        self.rows = self.rows[:1]
        self.write_log()
        self.run_dispatch("UserPromptSubmit")
        self.assertIsNone(self.run_dispatch("Stop"))
        key = hashlib.sha256(self.sid.encode()).hexdigest()
        (self.home / ".dsh/harness-cc-hooks" / (key + ".json")).write_text("broken")
        self.rows.append({"type": "turn/start", "seq": 20, "time": 1900000001000, "data": {"turn": 2}})
        self.write_log()
        self.run_dispatch("UserPromptSubmit")
        self.assertIsNone(self.run_dispatch("Stop"))

    def test_invalid_turn_boundary_never_arms_blocker(self):
        self.settings("Stop", [self.hook("print('{\"decision\":\"block\"}')")])
        del self.rows[1]["time"]
        self.write_log()
        self.run_dispatch("UserPromptSubmit")
        self.assertIsNone(self.run_dispatch("Stop"))

    def test_concurrent_stop_processes_emit_only_one_block(self):
        self.settings("Stop", [self.hook("import time; time.sleep(.1); print('{\"decision\":\"block\"}')")])
        self.run_dispatch("UserPromptSubmit")
        payload = json.dumps({"hook_event_name": "Stop", "session_id": self.sid, "cwd": str(self.root)})
        children = [subprocess.Popen([sys.executable, str(SCRIPT)], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                    env={**os.environ, "HOME": str(self.home), "PYTHONDONTWRITEBYTECODE": "1"})
                    for _ in range(4)]
        for child in children:
            child.stdin.write(payload)
            child.stdin.close()
            child.stdin = None
        outputs = [child.communicate(timeout=4) for child in children]
        self.assertEqual(sum(bool(out) for out, _ in outputs), 1)
        self.assertTrue(all(err == "" for _, err in outputs))
        self.assertTrue(all(child.returncode == 0 for child in children))

    def test_metadata_rejects_duplicate_id_wrong_header_and_bad_version(self):
        self.settings("SessionStart", [self.hook("print('UNSAFE')")])
        duplicate = self.home / ".dsh/sessions/other" / self.sid / "session.v4.jsonl.zstd"
        duplicate.parent.mkdir(parents=True)
        duplicate.write_bytes(self.log.read_bytes())
        self.assertIsNone(self.run_dispatch("SessionStart"))
        duplicate.unlink()
        for field, value in [("version", 3), ("id", "other-session"), ("cwd", "relative")]:
            with self.subTest(field=field):
                previous = self.rows[0][field]
                self.rows[0][field] = value
                self.write_log()
                self.assertIsNone(self.run_dispatch("SessionStart"))
                self.rows[0][field] = previous

    def test_real_top_header_omits_parent_session_but_bare_id_is_unknown(self):
        self.settings("SessionStart", [self.hook("print('KNOWN-TOP')")])
        del self.rows[0]["parentSession"]
        self.write_log()
        self.assertIn("KNOWN-TOP", str(self.run_dispatch("SessionStart")))
        self.sid = self.sid.removeprefix("session-")
        self.rows[0]["id"] = self.sid
        self.log = self.log.parent.parent / self.sid / "session.v4.jsonl.zstd"
        self.write_log()
        self.assertIsNone(self.run_dispatch("SessionStart"))

    def test_metadata_timeout_drops_partial_index(self):
        other = self.log.parent.parent / "second" / "session.v4.jsonl.zstd"
        other.parent.mkdir()
        other.write_bytes(zstd.compress((json.dumps({**self.rows[0], "id": "second"}) + "\n").encode()))
        with mock.patch.object(cc.time, "monotonic", side_effect=[0, 2]):
            metadata, records = cc.session_metadata(self.home, self.sid, 1, True)
        self.assertIsNotNone(metadata)
        self.assertEqual(records, [])

    def test_environment_and_recursive_child_paths(self):
        child = self.log.parent.parent / "child" / "session.v4.jsonl.zstd"
        grandchild = self.log.parent.parent / "grandchild" / "session.v4.jsonl.zstd"
        for path, parent in [(child, self.sid), (grandchild, "child")]:
            path.parent.mkdir()
            path.write_bytes(zstd.compress((json.dumps({**self.rows[0], "id": path.parent.name,
                                                       "parentSession": parent}) + "\n").encode()))
        code = "import json,sys; p=json.load(sys.stdin); print(json.dumps({'hookSpecificOutput':{'hookEventName':'SessionStart','additionalContext':json.dumps(p)}}))"
        self.settings("SessionStart", [self.hook(code)])
        payload = json.loads(self.run_dispatch("SessionStart")["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(set(payload["dsh_child_transcript_paths"]), {str(child), str(grandchild)})
        self.assertIsNone(payload["dsh_parent_session_id"])
        self.assertEqual(payload["dsh_transcript_path"], str(self.log))
        self.assertEqual(len(payload["dsh_session_records"]), 3)

    def test_shared_boundary_loading_has_no_output_or_file_writes(self):
        import io
        import contextlib
        before = sorted(str(path.relative_to(self.home)) for path in self.home.rglob("*"))
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            self.assertEqual(cc.current_turn(self.log, time.monotonic() + 2), [1, 1])
        self.assertEqual((output.getvalue(), errors.getvalue()), ("", ""))
        self.assertEqual(before, sorted(str(path.relative_to(self.home)) for path in self.home.rglob("*")))
        # compile/exec loads the actual shared source without import cache writes.
        with mock.patch.object(cc.hook_module("stop_evidence"), "turn_boundary", return_value=None):
            self.assertIsNone(cc.current_turn(self.log, time.monotonic() + 2))

    def test_proven_tool_input_aliases_preserve_native_fields(self):
        capture = "import json,sys; p=json.load(sys.stdin); print(json.dumps({'hookSpecificOutput':{'hookEventName':'PostToolUse','additionalContext':json.dumps(p['tool_input'])}}))"
        self.settings("PostToolUse", [self.hook(capture)])
        for source, values, expected in [
            ("bash", {"command": "true", "timeoutMs": 1234}, {"command": "true", "timeoutMs": 1234, "timeout": 1234}),
            ("web_search", {"queries": ["one"]}, {"queries": ["one"], "query": "one"}),
            ("web_search", {"queries": ["one", "two"]}, {"queries": ["one", "two"]}),
            ("grep", {"include": "*.py", "pattern": "x"}, {"glob": "*.py", "pattern": "x"}),
        ]:
            with self.subTest(source=source, values=values):
                output = self.run_dispatch("PostToolUse", tool_name=source, tool_input=values)
                self.assertEqual(json.loads(output["hookSpecificOutput"]["additionalContext"]), expected)

    def test_without_zstd_and_malformed_input_main_is_silent(self):
        import io
        import builtins
        import contextlib
        real_import = builtins.__import__
        def missing(name, *args, **kwargs):
            if name == "compression":
                raise ImportError("Python before 3.14")
            return real_import(name, *args, **kwargs)
        for raw in ["{", "[]", json.dumps({"hook_event_name": "SessionStart", "session_id": self.sid})]:
            stdout, stderr = io.StringIO(), io.StringIO()
            with mock.patch.dict(os.environ, {"HOME": str(self.home)}), mock.patch.object(cc.sys, "stdin", io.StringIO(raw)):
                with mock.patch("builtins.__import__", side_effect=missing), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    cc.main()
            self.assertEqual((stdout.getvalue(), stderr.getvalue()), ("", ""))

    def test_session_start_hard_budget_interrupts_slow_metadata_io(self):
        started = time.monotonic()
        with mock.patch.object(cc, "read_header", side_effect=lambda _path: time.sleep(2)):
            self.assertIsNone(cc.dispatch({"hook_event_name": "SessionStart", "session_id": self.sid}, self.home))
        elapsed = time.monotonic() - started
        self.assertGreaterEqual(elapsed, 0.75)
        self.assertLess(elapsed, 1.0)
        self.assertFalse((self.home / ".dsh/harness-cc-hooks").exists())

    def test_child_hook_duration_is_excluded_from_dispatch_budget(self):
        self.settings("SessionStart", [self.hook("import time; time.sleep(1); print('CONTEXT')")])
        started = time.monotonic()
        self.assertIn("CONTEXT", str(self.run_dispatch("SessionStart")))
        self.assertGreater(time.monotonic() - started, 1)

    def test_hook_cwd_changes_but_project_dir_keeps_created_root(self):
        subdir = self.root / "subdir"
        subdir.mkdir()
        self.settings("SessionStart", [self.hook("import os; print(os.getcwd() + '\\n' + os.environ['CLAUDE_PROJECT_DIR'])")])
        output = self.run_dispatch("SessionStart", cwd=str(subdir))["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(output, str(subdir) + "\n" + str(self.root))

    def test_explicit_timeout_uses_seconds_without_internal_cap(self):
        process = mock.Mock(returncode=0)
        process.communicate.return_value = (b"", b"")
        with mock.patch.object(cc.subprocess, "Popen", return_value=process):
            cc.run_command({"command": "true", "timeout": 900}, None,
                           {"hook_event_name": "Stop", "cwd": str(self.root)}, self.root)
        self.assertEqual(process.communicate.call_args.kwargs["timeout"], 900)

    def test_python39_runs_silently_without_creating_state(self):
        executable = Path("/usr/bin/python3")
        if not executable.exists():
            self.skipTest("Python 3.9 interpreter unavailable")
        version = subprocess.run([str(executable), "-c", "import sys;print(sys.version_info[:2])"], capture_output=True, text=True)
        if version.stdout.strip() != "(3, 9)":
            self.skipTest("system Python is not 3.9")
        self.settings("SessionStart", [self.hook("print('MUST-NOT-RUN')")])
        result = subprocess.run([str(executable), str(SCRIPT)],
                                input=json.dumps({"hook_event_name": "SessionStart", "session_id": self.sid}),
                                capture_output=True, text=True, timeout=3,
                                env={**os.environ, "HOME": str(self.home), "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
        self.assertFalse((self.home / ".dsh/harness-cc-hooks").exists())

    def test_dispatcher_termination_kills_running_hook_group(self):
        ready = self.home / "ready"
        late = self.home / "late"
        code = ("import pathlib,time; pathlib.Path(" + repr(str(ready)) + ").touch(); "
                "time.sleep(.6); pathlib.Path(" + repr(str(late)) + ").touch()")
        self.settings("SessionStart", [self.hook(code)])
        process = subprocess.Popen([sys.executable, str(SCRIPT)], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   env={**os.environ, "HOME": str(self.home), "PYTHONDONTWRITEBYTECODE": "1"})
        process.stdin.write(json.dumps({"hook_event_name": "SessionStart", "session_id": self.sid}))
        process.stdin.close()
        process.stdin = None
        deadline = time.monotonic() + 2
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(ready.exists())
        process.send_signal(signal.SIGTERM)
        output, error = process.communicate(timeout=2)
        self.assertEqual((process.returncode, output, error), (0, "", ""))
        time.sleep(.7)
        self.assertFalse(late.exists())


if __name__ == "__main__":
    unittest.main()
