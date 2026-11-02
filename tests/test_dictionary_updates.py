"""Stop reminds only for evidenced declaration changes to a registered responsibility."""

import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from unittest import mock

from hook_support import HookCase, REPO


BASE = 1_900_000_000_000_000_000
TABLE = "docs/rules/core-judgments.md"
MAP = "docs/rules/architecture.md"
SOURCE = "src/pricing.py"
BEFORE = "def floor_price(value):\n    return value\n"
AFTER = "def floor_price(value, fee=0):\n    return value - fee\n"


class DictionaryUpdatesTest(HookCase):
    def setUp(self):
        super().setUp()
        shutil.rmtree(self.root / ".git")
        self.git("init", "-q")
        self.write(SOURCE, BEFORE)
        self.write(TABLE, f"# 核心判断\n\n## 售价底线\n- 唯一实现:`{SOURCE}:floor_price`\n")
        self.git("add", "-A")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "--no-verify", "-m", "base")

    def git(self, *args):
        result = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True,
                                env={**os.environ, "HOME": str(self.home), "GIT_CONFIG_NOSYSTEM": "1"})
        self.assertEqual(result.returncode, 0, result.stderr)

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as stream:
            stream.write(text)
        return path

    def commit(self):
        self.git("add", "-A")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q",
                 "--allow-empty", "--no-verify", "-m", "base")

    def setup_source(self, path, name, before, after):
        self.write("docs/rules/core-judgments.md",
                   f"# 核心判断\n\n## 售价底线\n- 唯一实现:`{path}:{name}`\n")
        self.write(path, before)
        self.commit()
        self.write(path, after)

    def edit(self, relative=SOURCE, old=BEFORE, new=AFTER, *, error=False, call_id="edit", start=BASE + 200):
        return self.claude_call("Edit", {"file_path": str(self.root / relative),
                                        "old_string": old, "new_string": new},
                                start, start + 100, error=error, call_id=call_id)

    def stop(self, *rows, **extra):
        transcript = self.transcript(
            {"type": "user", "timestamp": self.stamp(BASE + 100),
             "message": {"role": "user", "content": "修改"}}, *rows)
        output = self.run_stop(self.stop_payload(transcript, **extra))
        if not output:
            return ""
        parsed = json.loads(output)
        return parsed.get("reason", parsed.get("hookSpecificOutput", {}).get("additionalContext", ""))

    def assert_update(self, output, name="floor_price", path=SOURCE, concept="售价底线"):
        self.assertIn("字典", output)
        self.assertIn(concept, output)
        self.assertIn(f"{path}:{name}", output)
        self.assertIn("docs/rules/harness.md「设计从整体到局部」", output)
        self.assertEqual(len(output.splitlines()), 1)

    def test_changed_definition_without_dictionary_edit_reminds(self):
        self.write(SOURCE, AFTER)
        self.assert_update(self.stop(*self.edit()))

    def test_body_only_even_with_definition_in_edit_is_silent(self):
        after = BEFORE.replace("return value", "return value + 1")
        self.write(SOURCE, after)
        self.assertEqual(self.stop(*self.edit(new=after)), "")
        self.assertEqual(self.stop(*self.edit(old="    return value", new="    return value + 1")), "")

    def test_inline_body_only_is_silent(self):
        self.assertEqual(self.stop(*self.edit(old="def floor_price(value): return value",
                                             new="def floor_price(value): return value + 1")), "")

    def test_docstring_definition_example_is_not_a_declaration(self):
        old = ('def floor_price(value):\n    """Example:\n'
               '    def floor_price(value): ...\n    """\n    return value\n')
        new = old.replace("    def floor_price(value): ...", "    def floor_price(value, fee=0): ...")
        self.setup_source(SOURCE, "floor_price", old, new)
        self.assertEqual(self.stop(*self.edit(old="def floor_price(value): ...",
                                               new="def floor_price(value, fee=0): ...")), "")

    def test_successful_table_or_map_edit_suppresses_the_reminder(self):
        self.write(SOURCE, AFTER)
        for relative in (TABLE, MAP):
            with self.subTest(relative=relative):
                rows = self.edit(relative, "old", "new", call_id="docs", start=BASE + 400)
                self.assertEqual(self.stop(*self.edit(), *rows), "")
                failed = self.edit(relative, "old", "new", error=True, call_id="docs", start=BASE + 400)
                self.assert_update(self.stop(*self.edit(), *failed))

    def test_unregistered_file_or_name_and_failed_edit_are_silent(self):
        for rows in (self.edit("src/other.py"), self.edit(old="def other():", new="def other(x):"),
                     self.edit(error=True)):
            with self.subTest(rows=rows):
                self.assertEqual(self.stop(*rows), "")

    def test_previous_turn_is_silent_but_mid_turn_message_does_not_erase_edits(self):
        self.write(SOURCE, AFTER)
        end = {"type": "system", "subtype": "turn_duration", "timestamp": self.stamp(BASE + 400)}
        self.assertEqual(self.stop(*self.edit(), end), "")
        notification = {"type": "user", "timestamp": self.stamp(BASE + 500),
                        "message": {"role": "user", "content": "<task-notification>done</task-notification>"}}
        self.assert_update(self.stop(*self.edit(), notification))
        self.assert_update(self.stop(*self.edit(TABLE, "old", "new", call_id="docs"), end,
                                     *self.edit(start=BASE + 600)))

    def test_added_removed_and_renamed_definitions_remind(self):
        for old, new in (("", BEFORE), (BEFORE, ""),
                         (BEFORE, BEFORE.replace("floor_price", "floor_value"))):
            with self.subTest(old=old, new=new):
                self.setup_source(SOURCE, "floor_price", old, new)
                self.assert_update(self.stop(*self.edit(old=old, new=new)))

    def test_multi_edit_and_write_compare_definitions(self):
        self.write(SOURCE, AFTER)
        rows = self.claude_call("MultiEdit", {"file_path": str(self.root / SOURCE), "edits": [
            {"old_string": BEFORE, "new_string": AFTER}]}, BASE + 200, BASE + 300)
        self.assert_update(self.stop(*rows))
        for content, reminds in ((AFTER, True), (BEFORE.replace("return value", "return value + 1"), False),
                                 (BEFORE.replace("floor_price", "floor_value"), True), ("def other():\n    pass\n", True),
                                 ("", True)):
            with self.subTest(content=content):
                self.write(SOURCE, content)
                rows = self.claude_call("Write", {"file_path": str(self.root / SOURCE), "content": content},
                                        BASE + 200, BASE + 300)
                output = self.stop(*rows)
                self.assert_update(output) if reminds else self.assertEqual(output, "")

    def codex(self, changes, *, completed=True):
        return (
            {"type": "event_msg", "timestamp": self.stamp(BASE + 100),
             "payload": {"type": "task_started", "turn_id": "turn-1"}},
            {"type": "event_msg", "timestamp": self.stamp(BASE + 300), "payload": {
                "type": "item_completed" if completed else "item_started", "item": {
                    "type": "FileChange", "changes": {str(self.root / p): change for p, change in changes.items()}}}},
        )

    def test_codex_filechange_plus_minus_and_document_edits(self):
        self.write(SOURCE, AFTER)
        change = {"type": "update", "unified_diff": "@@ -1 +1 @@\n-def floor_price(value):\n+def floor_price(value, fee=0):\n"}
        self.assert_update(self.stop(*self.codex({SOURCE: change}), turn_id="turn-1"))
        self.assertEqual(self.stop(*self.codex({SOURCE: change}, completed=False), turn_id="turn-1"), "")
        body = {"type": "update", "unified_diff": "@@ -2 +2 @@\n-    return value\n+    return value + 1\n"}
        self.write(SOURCE, BEFORE.replace("return value", "return value + 1"))
        self.assertEqual(self.stop(*self.codex({SOURCE: body}), turn_id="turn-1"), "")
        self.write(SOURCE, AFTER)
        for relative in (TABLE, MAP):
            self.assertEqual(self.stop(*self.codex({SOURCE: change, relative: {"type": "add", "content": "# updated\n"}}),
                                       turn_id="turn-1"), "")
        self.setup_source(SOURCE, "floor_price", "", BEFORE)
        self.assert_update(self.stop(*self.codex({SOURCE: {"type": "add", "content": BEFORE}}), turn_id="turn-1"))
        self.setup_source(SOURCE, "floor_price", BEFORE, "")
        (self.root / SOURCE).unlink()
        self.assert_update(self.stop(*self.codex({SOURCE: {"type": "delete", "content": BEFORE}}), turn_id="turn-1"))
        start = {"type": "event_msg", "timestamp": self.stamp(BASE + 500), "payload": {"type": "task_started"}}
        self.assertEqual(self.stop(*self.codex({SOURCE: change}), start, turn_id="turn-2"), "")

    def test_python_class_bases_and_module_constants(self):
        self.setup_source("src/policy.py", "Policy", "class Policy:\n    pass\n", "class Policy(Base):\n    pass\n")
        self.assert_update(self.stop(*self.edit("src/policy.py", "class Policy:", "class Policy(Base):")),
                           "Policy", "src/policy.py")
        old = "FLOOR_RATE = 0.05\n\nclass Policy:\n    LIMIT: int = 3\n"
        values = old.replace("0.05", "0.06").replace("= 3", "= 4")
        renamed = old.replace("FLOOR_RATE", "FLOOR_RATIO")
        removed = old.replace("    LIMIT: int = 3\n", "    pass\n")
        for name, new, reminds in (("FLOOR_RATE", values, False), ("LIMIT", values, False),
                                   ("FLOOR_RATE", renamed, True), ("LIMIT", renamed, False),
                                   ("LIMIT", removed, True), ("FLOOR_RATE", removed, False)):
            with self.subTest(name=name, new=new):
                self.setup_source("src/policy.py", name, old, new)
                output = self.stop(*self.edit("src/policy.py", old, new))
                if reminds:
                    self.assert_update(output, name, "src/policy.py")
                else:
                    self.assertEqual(output, "")

    def test_decorators_enclosing_scope_and_bom(self):
        method = "class P:\n    @staticmethod\n    def floor_price(value):\n        return value\n"
        for old, new in ((method, method.replace("    @staticmethod\n", "")),
                         (BEFORE, "class P:\n" + "".join("    " + line + "\n" for line in BEFORE.splitlines()))):
            with self.subTest(new=new):
                self.setup_source(SOURCE, "floor_price", old, new)
                self.assert_update(self.stop(*self.edit(old=old, new=new)))
        self.setup_source(SOURCE, "floor_price", "\ufeff" + BEFORE, "\ufeff" + AFTER)
        self.assert_update(self.stop(*self.edit()))
        body = "\ufeff" + BEFORE.replace("return value", "return value + 1")
        self.setup_source(SOURCE, "floor_price", "\ufeff" + BEFORE, body)
        self.assertEqual(self.stop(*self.edit(old="return value", new="return value + 1")), "")

    def test_codex_move_without_name_in_diff_reminds(self):
        moved = "src/renamed.py"
        self.write(moved, BEFORE)
        (self.root / SOURCE).unlink()
        for diff in ("", "@@ -2 +2 @@\n-    return value\n+    return value\n"):
            with self.subTest(diff=diff):
                rename = {"type": "update", "move_path": str(self.root / moved), "unified_diff": diff}
                self.assert_update(self.stop(*self.codex({SOURCE: rename}), turn_id="turn-1"))

    def test_project_below_git_top_level_uses_project_relative_table_paths(self):
        app = self.root / "app"
        (app / ".scratch").mkdir(parents=True)
        self.write(f"app/{TABLE}", f"## 售价底线\n- 唯一实现:`{SOURCE}:floor_price`\n")
        self.write(f"app/{SOURCE}", BEFORE)
        self.commit()
        self.write(f"app/{SOURCE}", AFTER)
        rows = self.edit(f"app/{SOURCE}")
        for extra, reminds in (((), True), (self.edit(f"app/{TABLE}", "old", "new", call_id="docs", start=BASE + 400), False)):
            with self.subTest(reminds=reminds):
                transcript = self.transcript({"type": "user", "timestamp": self.stamp(BASE + 100),
                                              "message": {"role": "user", "content": "修改"}}, *rows, *extra)
                output = self.run_stop({**self.stop_payload(transcript), "cwd": str(app)})
                text = json.loads(output).get("reason", "") if output else ""
                text = text or (json.loads(output).get("hookSpecificOutput", {}).get("additionalContext", "") if output else "")
                if reminds:
                    self.assert_update(text)
                else:
                    self.assertEqual(text, "")

    def test_local_assignment_with_registered_name_is_body(self):
        old = "def floor_price(value):\n    return value\n\ndef other():\n    x = 1\n    return x\n"
        new = old.replace("    x = 1\n    return x", "    floor_price = 1\n    return floor_price")
        self.setup_source(SOURCE, "floor_price", old, new)
        self.assertEqual(self.stop(*self.edit(old="    x = 1\n    return x",
                                               new="    floor_price = 1\n    return floor_price")), "")

    def test_script_files_are_not_compared(self):
        path = "src/price.ts"
        old = "export function floorPrice(value: number) {}"
        new = "export function floorPrice(value: number, fee = 0) {}"
        self.setup_source(path, "floorPrice", old, new)
        self.assertEqual(self.stop(*self.edit(path, old, new)), "")

    def test_registered_hook_file_is_not_excluded_as_agent_configuration(self):
        path = ".claude/hooks/local.py"
        self.setup_source(path, "floor_price", BEFORE, AFTER)
        self.assert_update(self.stop(*self.edit(path)), path=path)

    def test_subagent_evidence_is_limited_to_parent_turn(self):
        self.write(SOURCE, AFTER)
        child = self.root / ".claude/history/subagents/agent-a.jsonl"
        self.transcript(*self.edit(), path=child)
        self.assert_update(self.stop())
        self.transcript(*self.edit(start=BASE - 500), path=child)
        self.assertEqual(self.stop(), "")

    def test_error_timeout_and_active_stop_keep_existing_task_contract(self):
        hook_dir = str(REPO / ".claude/hooks")
        sys.path.insert(0, hook_dir)
        try:
            import dictionary_updates
            import stop_guard
            transcript = self.transcript(*self.edit())
            payload = self.stop_payload(transcript)
            for error in (TimeoutError("budget"), RuntimeError("parse")):
                with mock.patch.object(dictionary_updates, "reminder", side_effect=error), \
                        mock.patch.object(stop_guard, "task_reminder", return_value="[harness] existing"), \
                        mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))):
                    result = stop_guard.main()
                    self.assertEqual(result["hookSpecificOutput"]["additionalContext"], "[harness] existing")
            with mock.patch.object(dictionary_updates, "TIME_BUDGET", -1):
                self.assertIsNone(stop_guard.dictionary_reminder(payload, self.root, self.root))
        finally:
            sys.path.remove(hook_dir)
        self.assertEqual(self.stop(*self.edit(), stop_hook_active=True), "")

    def test_multiline_python_argument_change_from_partial_edit(self):
        old = "def floor_price(\n    value,\n):\n    return value\n"
        new = "def floor_price(\n    value,\n    fee=0,\n):\n    return value - fee\n"
        self.setup_source(SOURCE, "floor_price", old, new)
        self.assert_update(self.stop(*self.edit(old="floor_price(\n    value,",
                                                new="floor_price(\n    value,\n    fee=0,")))

    def test_inconsistent_fragment_indentation_still_detects_whole_file_change(self):
        self.write(SOURCE, AFTER)
        self.assert_update(self.stop(*self.edit(old="    def floor_price(value):",
                                                new="def floor_price(value, fee=0):")))

    def test_nested_python_definition_counts_even_with_same_named_top_level(self):
        old = ("def outer():\n    def floor_price(value):\n        return value\n"
               "    return floor_price(1)\n\n"
               "def floor_price(value):\n    return value\n")
        new = old.replace("    def floor_price(value):", "    def floor_price(value, fee=0):")
        self.setup_source(SOURCE, "floor_price", old, new)
        self.assert_update(self.stop(*self.edit(old="def floor_price(value)",
                                                new="def floor_price(value, fee=0)")))

    def test_identical_python_definition_multiplicity_and_return_annotation(self):
        old = ("def floor_price(value: int) -> int:\n    return value\n\n"
               "def floor_price(value: int) -> int:\n    return value\n")
        new = "def floor_price(value: int) -> int:\n    return value\n"
        self.setup_source(SOURCE, "floor_price", old, new)
        self.assert_update(self.stop(*self.edit(old=old, new=new)))
        self.setup_source(SOURCE, "floor_price", new,
                          "def floor_price(value: int) -> float:\n    return value\n")
        self.assert_update(self.stop(*self.edit(old="floor_price(value: int) -> int",
                                                new="floor_price(value: int) -> float")))

    def test_codex_multihunk_and_move_path_source(self):
        self.write(SOURCE, AFTER)
        change = {"type": "update", "unified_diff": (
            "@@ -1 +1 @@\n-def floor_price(value):\n+def floor_price(value, fee=0):\n"
            "@@ -2 +2 @@\n-    return value\n+    return value - fee\n")}
        self.assert_update(self.stop(*self.codex({SOURCE: change}), turn_id="turn-1"))
        moved = "src/renamed.py"
        self.write(moved, BEFORE)
        (self.root / SOURCE).unlink()
        rename = {"type": "update", "move_path": str(self.root / SOURCE),
                  "unified_diff": "@@ -1 +1 @@\n-def floor_price(value):\n+def floor_price(value):\n"}
        self.assert_update(self.stop(*self.codex({moved: rename}), turn_id="turn-1"))
        self.write(SOURCE, BEFORE)
        self.commit()
        self.write(moved, BEFORE)
        (self.root / SOURCE).unlink()
        rename = {"type": "update", "move_path": str(self.root / moved),
                  "unified_diff": "@@ -1 +1 @@\n-def floor_price(value):\n+def floor_price(value):\n"}
        self.assert_update(self.stop(*self.codex({SOURCE: rename}), turn_id="turn-1"))

    def test_head_absent_invalid_whole_file_and_delete(self):
        path = "src/new.py"
        self.write(TABLE, f"## 售价底线\n- 唯一实现:`{path}:floor_price`\n")
        self.write(path, AFTER)
        self.assertEqual(self.stop(*self.edit(path, "", AFTER)), "")
        self.write(TABLE, f"## 售价底线\n- 唯一实现:`{SOURCE}:floor_price`\n")
        self.write(SOURCE, "def floor_price(:\n")
        self.assertEqual(self.stop(*self.edit(old=BEFORE, new="def floor_price(:")), "")
        (self.root / SOURCE).unlink()
        self.assert_update(self.stop(*self.codex({SOURCE: {"type": "delete"}}), turn_id="turn-1"))
        self.assert_update(self.stop(*self.codex({SOURCE: {"type": "delete", "content": BEFORE}}),
                                     turn_id="turn-1"))
        self.write(SOURCE, "def floor_price(:\n")
        self.commit()
        self.write(SOURCE, AFTER)
        self.assertEqual(self.stop(*self.edit(old="def floor_price(:", new=AFTER)), "")

    def test_prior_committed_change_and_stale_uncommitted_change(self):
        self.write(SOURCE, AFTER)
        self.commit()
        body = AFTER.replace("return value - fee", "return value + fee")
        self.write(SOURCE, body)
        self.assertEqual(self.stop(*self.edit(old=AFTER, new=body)), "")
        self.write(SOURCE, BEFORE)
        self.assert_update(self.stop(*self.edit(old="def floor_price(value):",
                                                new="def floor_price(value):  # touched floor_price")))

    def test_fullwidth_colon_with_crlf_table(self):
        self.write(TABLE, "# 核心判断\r\n\r\n## 售价底线\r\n"
                          f"- 唯一实现：`{SOURCE}:floor_price`\r\n")
        self.write(SOURCE, AFTER)
        self.assert_update(self.stop(*self.edit()))


if __name__ == "__main__":
    unittest.main()
