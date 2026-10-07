import json
import unittest

from hook_support import HookCase


class StopCommandParsingTest(HookCase):
    """Stop 兜底从 shell、Codex JS 与函数调用参数里识别点名文件和 git 子命令。"""

    def test_shell_words_keep_quoted_and_escaped_spaces_together(self):
        cases = (
            ('cat "my app.py"', "app.py", False),
            ("cat > \"my app.py\" <<'EOF'", "my app.py", True),
            (r"cat > my\ app.py", "my app.py", True),
            ("echo don't; cat > out.txt", "out.txt", True),
        )
        for command, filename, blocked in cases:
            with self.subTest(command=command, filename=filename):
                self.reset_root()
                _, _, unused, base = self.stop_fixture()
                candidate = self.root / filename
                candidate.write_text("x", encoding="utf-8")
                self.set_mtime(candidate, base + 300)
                self.transcript(*self.claude_call(
                    "Bash", {"command": command}, base + 200, base + 400))
                output = self.run_stop()
                if blocked:
                    self.assert_block(output, "active")
                else:
                    self.assertEqual(output, "")

    def test_git_options_and_executable_path_identify_real_subcommand(self):
        cases = (
            ("git -P merge topic", True),
            ("git --work-tree . restore .", True),
            ("git --no-pager merge topic", True),
            ('/usr/bin/git -C "/a b" merge x', True),
            ("git status", False),
            ('git commit -m "git merge later"', False),
        )
        for command, blocked in cases:
            with self.subTest(command=command):
                self.reset_root()
                _, _, code, base = self.stop_fixture()
                self.transcript(*self.claude_call(
                    "Bash", {"command": command}, base + 200, base + 400))
                output = self.run_stop()
                if blocked:
                    self.assert_block(output, "active")
                else:
                    self.assertEqual(output, "")

    def test_codex_exec_js_string_literals_preserve_spaces_and_escapes(self):
        cases = (
            (r'await tools.exec_command({cmd:"cat > \"my app.py\""})', True),
            ('await tools.exec_command({cmd:"cat my app.py"})', False),
        )
        for source, blocked in cases:
            with self.subTest(source=source):
                self.reset_root()
                _, _, unused, base = self.stop_fixture()
                candidate = self.root / "my app.py"
                candidate.write_text("x", encoding="utf-8")
                self.set_mtime(candidate, base + 300)
                self.transcript(
                    {"type": "response_item", "timestamp": self.stamp(base + 200),
                     "payload": {"type": "custom_tool_call", "call_id": "js-space",
                                 "name": "exec", "input": source}},
                    {"type": "response_item", "timestamp": self.stamp(base + 400),
                     "payload": {"type": "custom_tool_call_output", "call_id": "js-space",
                                 "output": "done"}},
                )
                output = self.run_stop()
                if blocked:
                    self.assert_block(output, "active")
                else:
                    self.assertEqual(output, "")

    def test_codex_function_call_json_values_and_invalid_json_raw_text(self):
        for arguments, filename in (
                (json.dumps({"cmd": "cat > 'my app.py'"}), "my app.py"),
                ('{"cmd": cat > out.txt', "out.txt")):
            with self.subTest(arguments=arguments):
                self.reset_root()
                _, _, unused, base = self.stop_fixture()
                candidate = self.root / filename
                candidate.write_text("x", encoding="utf-8")
                self.set_mtime(candidate, base + 300)
                self.transcript(
                    {"type": "response_item", "timestamp": self.stamp(base + 200),
                     "payload": {"type": "function_call", "call_id": "json-space",
                                 "name": "exec_command", "arguments": arguments}},
                    {"type": "response_item", "timestamp": self.stamp(base + 400),
                     "payload": {"type": "function_call_output", "call_id": "json-space",
                                 "output": "done"}},
                )
                self.assert_block(self.run_stop(), "active")

    def test_codex_local_shell_command_array_preserves_quoted_path(self):
        _, _, unused, base = self.stop_fixture()
        candidate = self.root / "my app.py"
        candidate.write_text("x", encoding="utf-8")
        self.set_mtime(candidate, base + 300)
        self.transcript(
            {"type": "response_item", "timestamp": self.stamp(base + 200),
             "payload": {"type": "local_shell_call", "call_id": "shell-space",
                         "action": {"command": ["bash", "-lc",
                                                "cat > 'my app.py'"]}}},
            {"type": "response_item", "timestamp": self.stamp(base + 400),
             "payload": {"type": "function_call_output", "call_id": "shell-space",
                         "output": "done"}},
        )
        self.assert_block(self.run_stop(), "active")

    def test_codex_js_single_quote_template_and_string_escapes(self):
        sources = (
            """await tools.exec_command({cmd:'cat > "my app.py"'})""",
            "await tools.exec_command({cmd:`cat >\n'my app.py'`})",
            r'await tools.exec_command({cmd:"cat > \u0022my app.py\u0022"})',
            r'await tools.exec_command({cmd:"cat >\n\u0027my app.py\u0027"})',
            r'await tools.exec_command({cmd:"cat >\t\u0027my app.py\u0027"})',
        )
        for source in sources:
            with self.subTest(source=source):
                self.reset_root()
                _, _, unused, base = self.stop_fixture()
                candidate = self.root / "my app.py"
                candidate.write_text("x", encoding="utf-8")
                self.set_mtime(candidate, base + 300)
                self.transcript(
                    {"type": "response_item", "timestamp": self.stamp(base + 200),
                     "payload": {"type": "custom_tool_call", "call_id": "js-escape",
                                 "name": "exec", "input": source}},
                    {"type": "response_item", "timestamp": self.stamp(base + 400),
                     "payload": {"type": "custom_tool_call_output", "call_id": "js-escape",
                                 "output": "done"}},
                )
                self.assert_block(self.run_stop(), "active")

    def test_codex_function_call_recurses_into_nested_json_strings(self):
        _, _, unused, base = self.stop_fixture()
        candidate = self.root / "my app.py"
        candidate.write_text("x", encoding="utf-8")
        self.set_mtime(candidate, base + 300)
        self.transcript(
            {"type": "response_item", "timestamp": self.stamp(base + 200),
             "payload": {"type": "function_call", "call_id": "nested",
                         "name": "exec_command", "arguments": json.dumps({
                             "outer": [{"command": "cat > 'my app.py'"}]})}},
            {"type": "response_item", "timestamp": self.stamp(base + 400),
             "payload": {"type": "function_call_output", "call_id": "nested",
                         "output": "done"}},
        )
        self.assert_block(self.run_stop(), "active")

    def test_local_shell_array_element_is_a_word(self):
        self.stop_fixture()
        candidate = self.root / "my app.py"
        candidate.write_text("x", encoding="utf-8")
        base = 1_900_000_000_000_000_000
        self.set_mtime(candidate, base + 300)
        self.transcript(
            {"type": "response_item", "timestamp": self.stamp(base + 200),
             "payload": {"type": "local_shell_call", "call_id": "array-word",
                         "action": {"command": ["bash", "my app.py"]}}},
            {"type": "response_item", "timestamp": self.stamp(base + 400),
             "payload": {"type": "function_call_output", "call_id": "array-word",
                         "output": "done"}},
        )
        self.assert_block(self.run_stop(), "active")

    def test_unclosed_shell_quote_does_not_swallow_next_line(self):
        _, _, unused, base = self.stop_fixture()
        out = self.root / "out.txt"
        out.write_text("x", encoding="utf-8")
        self.set_mtime(out, base + 300)
        self.transcript(*self.claude_call(
            "Bash", {"command": "echo 'unterminated\ncat > out.txt"},
            base + 200, base + 400))
        self.assert_block(self.run_stop(), "active")

    def test_unquoted_filename_slices_match_after_option_and_line_suffix(self):
        for command, filename in (("cat --output=dir/x.txt", "x.txt"),
                                  ("cat file.py:12", "file.py"),
                                  ("cat files=[dir/x.txt]", "x.txt")):
            with self.subTest(command=command):
                self.reset_root()
                _, _, unused, base = self.stop_fixture()
                candidate = self.root / filename
                candidate.write_text("x", encoding="utf-8")
                self.set_mtime(candidate, base + 300)
                self.transcript(*self.claude_call(
                    "Bash", {"command": command}, base + 200, base + 400))
                self.assert_block(self.run_stop(), "active")

    def test_quoted_filename_keeps_punctuation_as_one_word(self):
        for quoted_name in ("prefix=app.py", "prefix:app.py", "prefix,app.py",
                            "prefix[app.py]", "prefix{app.py}"):
            with self.subTest(quoted_name=quoted_name):
                self.reset_root()
                _, _, unused, base = self.stop_fixture()
                candidate = self.root / "app.py"
                candidate.write_text("x", encoding="utf-8")
                self.set_mtime(candidate, base + 300)
                self.transcript(*self.claude_call(
                    "Bash", {"command": f'cat "{quoted_name}"'},
                    base + 200, base + 400))
                self.assertEqual(self.run_stop(), "")

        self.reset_root()
        _, _, unused, base = self.stop_fixture()
        candidate = self.root / "prefix=:[,]{}app.py"
        candidate.write_text("x", encoding="utf-8")
        self.set_mtime(candidate, base + 300)
        self.transcript(*self.claude_call(
            "Bash", {"command": f'cat "{candidate.name}"'},
            base + 200, base + 400))
        self.assert_block(self.run_stop(), "active")

    def test_git_subcommand_cannot_cross_command_boundaries(self):
        for separator in (";", "\n", "&", "|", "&&", "||", "|&", "(", ")"):
            with self.subTest(separator=separator):
                self.reset_root()
                _, _, unused, base = self.stop_fixture()
                command = f"git -P {separator} merge topic"
                self.transcript(*self.claude_call(
                    "Bash", {"command": command}, base + 200, base + 400))
                self.assertEqual(self.run_stop(), "")

        for command in ("git -P; git merge topic",
                        "git -P\n/usr/bin/git merge topic"):
            with self.subTest(command=command):
                self.reset_root()
                _, _, unused, base = self.stop_fixture()
                self.transcript(*self.claude_call(
                    "Bash", {"command": command}, base + 200, base + 400))
                self.assert_block(self.run_stop(), "active")

    def test_redirection_ampersand_greater_than_is_not_git_boundary(self):
        _, _, unused, base = self.stop_fixture()
        self.transcript(*self.claude_call(
            "Bash", {"command": "git -C /x &> merge feat"},
            base + 200, base + 400))
        self.assert_block(self.run_stop(), "active")

    def test_git_option_missing_argument_does_not_cross_command_boundary(self):
        for command in ("git -C; merge topic", "git --work-tree\nmerge topic",
                        "git -c && merge topic"):
            with self.subTest(command=command):
                self.reset_root()
                _, _, code, base = self.stop_fixture()
                self.transcript(*self.claude_call(
                    "Bash", {"command": command}, base + 200, base + 400))
                self.assertEqual(self.run_stop(), "")

    def test_unclosed_double_quote_with_backslash_newline_does_not_hide_next_line(self):
        _, _, code, base = self.stop_fixture()
        command = 'echo "unterminated' + '\\' + '\n' + 'cat > changed.py"'
        self.assertIn('\\\n', command)
        self.transcript(*self.claude_call(
            "Bash", {"command": command}, base + 200, base + 400))
        self.assert_block(self.run_stop(), "active")

    def test_codex_exec_js_comments_do_not_supply_command_evidence(self):
        cases = (
            ('// "cat > changed.py"\nawait tools.exec_command({cmd:"echo okay"})', False),
            ('/* "cat > changed.py" */\nawait tools.exec_command({cmd:"echo okay"})', False),
            ('await tools.exec_command({cmd:"cat > \'/tmp//changed.py\'"})', True),
        )
        for source, blocked in cases:
            with self.subTest(source=source):
                self.reset_root()
                _, _, code, base = self.stop_fixture()
                self.transcript(
                    {"type": "response_item", "timestamp": self.stamp(base + 200),
                     "payload": {"type": "custom_tool_call", "call_id": "js-comment",
                                 "name": "exec", "input": source}},
                    {"type": "response_item", "timestamp": self.stamp(base + 400),
                     "payload": {"type": "custom_tool_call_output", "call_id": "js-comment",
                                 "output": "done"}},
                )
                output = self.run_stop()
                if blocked:
                    self.assert_block(output, "active")
                else:
                    self.assertEqual(output, "")


if __name__ == "__main__":
    unittest.main()
