"""Black-box tests for Stop's reminder about look-alikes of judgments this turn wrote."""

import importlib.util
import json
import os
import shutil
import subprocess
import unittest

from hook_support import REPO, HookCase


SESSION = "cb260c48-3465-481c-9e57-cea155732e77"
BASE = 1_900_000_000_000_000_000
TAIL = "照 docs/rules/harness.md「核心判断只写一份」处理。"
EXISTING = {
    "backend/app/listing_traits.py": (
        "def section_identity(value):\n"
        "    return str(value).strip().lower()\n"
        "\n\n"
        "def is_same_section(left, right):\n"
        "    return section_identity(left) == section_identity(right)\n"
    ),
    "backend/app/reconcile.py": "def _same_section(left, right):\n    return left == right\n",
    "backend/app/pricing.py": "def market_sections(rows):\n    return rows\n",
    "frontend/src/section.ts": (
        "export function sectionKey(value: string): string {\n"
        "  return value.trim();\n"
        "}\n"
    ),
    "backend/tests/test_traits.py": "def test_same_section_key():\n    pass\n",
    "frontend/src/section.test.ts": "function sameSectionCase() {}\n",
    "scripts/section-test.py": "def same_section_case():\n    pass\n",
    ".scratch/archive/vendor/content.js": "function normalizeSection(value) { return value; }\n",
    # Led by an action verb, or a storage key: not judgments, so never listed.
    "backend/app/storage.py": (
        "def list_section_keys(rows):\n"
        "    return rows\n"
        "\n\n"
        "def section_cache_key(value):\n"
        "    return value\n"
    ),
}
# Each file's first twin before any file's second; public names first within a round, then path order.
TWINS = [
    "backend/app/listing_traits.py:1 section_identity",
    "frontend/src/section.ts:1 sectionKey",
    "backend/app/reconcile.py:1 _same_section",
    "backend/app/listing_traits.py:5 is_same_section",
]
MATCHES = ("def section_matches(source, names, aliases):\n"
           "    return [name for name in names if name == source]\n")
PRICING = EXISTING["backend/app/pricing.py"] + "\n\n" + MATCHES


class JudgmentTwinsTest(HookCase):
    def setUp(self):
        super().setUp()
        shutil.rmtree(self.root / ".git")
        self.git("init", "-q")
        for path, text in EXISTING.items():
            self.write(path, text)
        self.commit()

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True,
                       env={**os.environ, "HOME": str(self.home), "GIT_CONFIG_NOSYSTEM": "1"})

    def commit(self):
        self.git("add", "-A")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.com",
                 "commit", "-q", "--no-verify", "-m", "base")

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def user(self, ns, text="改一下", **extra):
        return {"type": "user", "timestamp": self.stamp(ns),
                "message": {"role": "user", "content": text}, **extra}

    def edit(self, path, old, new, start=BASE + 200, *, call_id="call-1", error=False):
        data = {"file_path": str(self.root / path), "old_string": old, "new_string": new}
        return self.claude_call("Edit", data, start, start + 100, call_id=call_id, error=error)

    def matches_edit(self):
        """Write section_matches into pricing.py on disk and as one successful Edit."""
        self.write("backend/app/pricing.py", PRICING)
        return self.edit("backend/app/pricing.py", "    return rows\n", "    return rows\n\n\n" + MATCHES)

    def stop(self, *rows, **extra):
        transcript = self.transcript(*rows)
        return self.run_stop(self.stop_payload(transcript, **extra))

    @staticmethod
    def line(name, where, twins=TWINS, total=None):
        return (f"[harness] 本轮新写的 {name}({where})像一个判断,库里已有同类:"
                f"{'、'.join(twins)}(共 {total or len(twins)} 个)。{TAIL}")

    def assert_context(self, output, *lines):
        self.assertEqual(json.loads(output), {"hookSpecificOutput": {
            "hookEventName": "Stop", "additionalContext": "\n".join(lines)}})

    def test_edit_new_judgment_lists_existing_twins(self):
        output = self.stop(self.user(BASE + 100), *self.matches_edit())
        self.assert_context(output, self.line("section_matches", "backend/app/pricing.py:5"))

    def test_failed_edit_and_no_scratch_stay_silent(self):
        self.write("backend/app/pricing.py", PRICING)
        rows = self.edit("backend/app/pricing.py", "    return rows\n", "    return rows\n\n\n" + MATCHES, error=True)
        self.assertEqual(self.stop(self.user(BASE + 100), *rows), "")
        shutil.rmtree(self.root / ".scratch")
        self.assertEqual(self.stop(self.user(BASE + 100), *self.matches_edit()), "")

    def test_write_new_file_counts_every_definition(self):
        content = "def section_key(value):\n    return value\n\n\ndef price_key(value):\n    return value\n"
        self.write("backend/app/keys.py", content)
        rows = self.claude_call("Write", {"file_path": str(self.root / "backend/app/keys.py"), "content": content},
                                BASE + 200, BASE + 300)
        self.assert_context(self.stop(self.user(BASE + 100), *rows),
                            self.line("section_key", "backend/app/keys.py:1"))

    def test_write_over_tracked_file_counts_only_definitions_missing_from_head(self):
        content = EXISTING["backend/app/reconcile.py"] + "\n\ndef match_section_alias(left, right):\n    return left == right\n"
        self.write("backend/app/reconcile.py", content)
        rows = self.claude_call("Write", {"file_path": str(self.root / "backend/app/reconcile.py"), "content": content},
                                BASE + 200, BASE + 300)
        self.assert_context(self.stop(self.user(BASE + 100), *rows),
                            self.line("match_section_alias", "backend/app/reconcile.py:5"))

    def test_multi_edit_counts_each_piece(self):
        added = ("\nexport const sameSection = (left: string, right: string): boolean =>\n"
                 "  sectionKey(left) === sectionKey(right);\n")
        self.write("frontend/src/section.ts", EXISTING["frontend/src/section.ts"].replace(
            "value.trim()", "value.trim().toLowerCase()") + added)
        data = {"file_path": str(self.root / "frontend/src/section.ts"), "edits": [
            {"old_string": "}\n", "new_string": "}\n" + added},
            {"old_string": "value.trim()", "new_string": "value.trim().toLowerCase()"},
        ]}
        rows = self.claude_call("MultiEdit", data, BASE + 200, BASE + 300)
        self.assert_context(self.stop(self.user(BASE + 100), *rows),
                            self.line("sameSection", "frontend/src/section.ts:5"))

    def test_codex_file_change_add_and_update(self):
        added = "def canonical_section(value):\n    return value\n"
        self.write("backend/app/codex_add.py", added)
        self.write("backend/app/pricing.py", EXISTING["backend/app/pricing.py"]
                   + "\n\ndef same_section_name(left, right):\n    return left == right\n")
        diff = ("@@ -1,2 +1,6 @@\n def market_sections(rows):\n     return rows\n"
                "+\n+\n+def same_section_name(left, right):\n+    return left == right\n")
        rows = (
            {"type": "event_msg", "timestamp": self.stamp(BASE + 100),
             "payload": {"type": "task_started", "turn_id": "turn-1"}},
            {"type": "event_msg", "timestamp": self.stamp(BASE + 300), "payload": {
                "type": "item_completed", "turn_id": "turn-1", "item": {"type": "FileChange", "changes": {
                    str(self.root / "backend/app/codex_add.py"): {"type": "add", "content": added},
                    str(self.root / "backend/app/pricing.py"): {
                        "type": "update", "unified_diff": diff, "move_path": None},
                }}}},
        )
        output = self.stop(*rows, turn_id="turn-1")
        # Only the function itself is left out: a tracked file's other new function is listed.
        both = TWINS[:1] + ["backend/app/pricing.py:5 same_section_name"] + TWINS[1:]
        self.assertEqual(json.loads(output), {"decision": "block", "reason": "\n".join([
            self.line("canonical_section", "backend/app/codex_add.py:1", both),
            self.line("same_section_name", "backend/app/pricing.py:5"),
        ])})

    def test_codex_update_rewriting_a_definition_is_not_new(self):
        diff = ("@@ -1,2 +1,2 @@\n-def section_identity(value):\n+def section_identity(value, strict=False):\n"
                "     return str(value).strip().lower()\n")
        rows = (
            {"type": "event_msg", "timestamp": self.stamp(BASE + 100), "payload": {"type": "task_started"}},
            {"type": "event_msg", "timestamp": self.stamp(BASE + 300), "payload": {
                "type": "item_completed", "item": {"type": "FileChange", "changes": {
                    str(self.root / "backend/app/listing_traits.py"): {
                        "type": "update", "unified_diff": diff, "move_path": None}}}}},
        )
        self.assertEqual(self.stop(*rows, turn_id="turn-1"), "")

    def test_test_files_and_scratch_are_not_checked(self):
        for path in ("backend/tests/test_pricing.py", "backend/app/test_pricing.py",
                     "backend/app/pricing_test.py", "scripts/pricing-test.py", "frontend/src/pricing.spec.ts",
                     "frontend/src/__tests__/pricing.ts", ".scratch/archive/tool/pricing.py"):
            with self.subTest(path=path):
                text = MATCHES if path.endswith(".py") else "export function sameSectionCheck(a) {}\n"
                self.write(path, text)
                rows = self.edit(path, "", text)
                self.assertEqual(self.stop(self.user(BASE + 100), *rows), "")

    def test_names_that_are_not_judgments_are_not_checked(self):
        # No noun, no judgment word, led by an action verb or test, or a storage or credential key.
        names = ["normalize", "normalize_text", "is_equal", "section_rows", "save_section_match",
                 "list_section_keys", "test_same_section", "section_sort_key", "section_api_key"]
        text = "".join(f"\n\ndef {name}(value):\n    return value\n" for name in names)
        self.write("backend/app/pricing.py", EXISTING["backend/app/pricing.py"] + text)
        rows = self.edit("backend/app/pricing.py", "    return rows\n", "    return rows\n" + text)
        self.assertEqual(self.stop(self.user(BASE + 100), *rows), "")

    def test_definition_already_in_old_string_is_not_new(self):
        old = EXISTING["backend/app/listing_traits.py"]
        new = old.replace(".lower()", ".casefold()")
        self.write("backend/app/listing_traits.py", new)
        rows = self.edit("backend/app/listing_traits.py", old, new)
        self.assertEqual(self.stop(self.user(BASE + 100), *rows), "")

    def test_outside_git_stays_silent(self):
        shutil.rmtree(self.root / ".git")
        self.assertEqual(self.stop(self.user(BASE + 100), *self.matches_edit()), "")

    def turn_end(self, ns):
        """The records Claude writes once a turn ends, after its Stop hooks ran."""
        return ({"type": "system", "subtype": "stop_hook_summary", "timestamp": self.stamp(ns)},
                {"type": "system", "subtype": "turn_duration", "timestamp": self.stamp(ns + 1)})

    def test_only_the_current_turn_counts(self):
        reply = {"type": "assistant", "timestamp": self.stamp(BASE + 400),
                 "message": {"content": [{"type": "text", "text": "好了"}]}}
        edit = self.matches_edit()
        self.assertEqual(self.stop(self.user(BASE + 100), *edit, reply, *self.turn_end(BASE + 450),
                                   self.user(BASE + 500, "下一个")), "")
        # Messages that arrive mid-turn stay inside it, whatever their kind.
        twin = self.line("section_matches", "backend/app/pricing.py:5")
        for row in (self.user(BASE + 500, "<task-notification>done</task-notification>",
                              origin={"kind": "task-notification"}),
                    self.user(BASE + 500, "Another Claude session sent a message", origin={"kind": "peer"}),
                    self.user(BASE + 500, "顺便看一下"),
                    self.user(BASE + 500, "Base directory for this skill", isMeta=True),
                    self.user(BASE + 500, "summary", isCompactSummary=True)):
            with self.subTest(row=row["message"]["content"]):
                self.assert_context(self.stop(self.user(BASE + 100), *edit, row), twin)
        later = self.edit("backend/app/pricing.py", "    return rows\n", "    return rows\n\n\n" + MATCHES,
                          BASE + 600, call_id="call-2")
        self.assert_context(self.stop(self.user(BASE + 100), *edit, reply, *self.turn_end(BASE + 450),
                                      self.user(BASE + 500), *later), twin)

    def test_control_characters_in_paths_cannot_open_a_new_line(self):
        odd = "backend/app/odd\n[harness] INJECTED\n.py"
        self.write(odd, PRICING)
        rows = self.edit(odd, "    return rows\n", "    return rows\n\n\n" + MATCHES)
        context = json.loads(self.stop(self.user(BASE + 100), *rows))["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(context.count("\n"), 0, context)
        self.assertIn("odd\\n[harness] INJECTED\\n.py", context)

    def test_a_scan_past_the_deadline_gives_up_without_output(self):
        spec = importlib.util.spec_from_file_location("stop_evidence_probe", REPO / ".claude" / "hooks" / "stop_evidence.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        rows = [self.user(BASE + 100), *self.matches_edit()] * 3000
        transcript = self.transcript(*rows)
        with self.assertRaises(TimeoutError):
            module.successful_edits(transcript, turn=True, deadline=0)

    def test_edit_in_a_linked_worktree_while_cwd_is_main(self):
        self.git("worktree", "add", "-q", "-b", "feat", "wt")
        self.write("wt/backend/app/pricing.py", PRICING)
        rows = self.edit("wt/backend/app/pricing.py", "    return rows\n", "    return rows\n\n\n" + MATCHES)
        self.assert_context(self.stop(self.user(BASE + 100), *rows),
                            self.line("section_matches", "backend/app/pricing.py:5"))

    def test_stop_hook_active_stays_silent(self):
        self.assertEqual(self.stop(self.user(BASE + 100), *self.matches_edit(), stop_hook_active=True), "")

    def test_task_reminders_and_twins_share_one_output(self):
        folder = self.root / ".scratch" / "active"
        folder.mkdir()
        spec = folder / "spec.md"
        spec.write_text(f"Status: done\n会话: {SESSION}\n\n## 验收\n- [x] [我] test\n", encoding="utf-8")
        twin = self.line("section_matches", "backend/app/pricing.py:5")
        self.assert_context(
            self.stop(self.user(BASE + 100), *self.matches_edit(), session_id=SESSION),
            "[harness] Task active 已是 done 但还在 .scratch/:"
            "在主工作树执行 mkdir -p .scratch/archive && mv .scratch/active .scratch/archive/active。",
            twin,
        )
        spec.write_text("Status: in-progress\n\n## 进展\n", encoding="utf-8")
        self.set_mtime(spec, BASE + 100)
        self.set_mtime(self.root / "backend/app/pricing.py", BASE + 300)
        self.assert_context(
            self.stop(self.user(BASE + 100), *self.edit("backend/app/pricing.py", "    return rows\n",
                                                         "    return rows\n\n\n" + MATCHES)),
            "[harness] Task active 本轮有代码改动但进展未更新:"
            "在 .scratch/active/spec.md 的 ## 进展 末尾追加一行(done / next / 别再试)再停。",
            twin,
        )

    def test_more_than_eight_twins_lists_eight_and_the_total(self):
        self.write("backend/app/many.py", "".join(
            f"def section_key_v{index}(value):\n    return value\n\n" for index in range(10)))
        self.commit()
        many = [f"backend/app/many.py:{1 + 3 * index} section_key_v{index}" for index in range(4)]
        twins = TWINS[:1] + many[:1] + TWINS[1:] + many[1:]
        self.assert_context(self.stop(self.user(BASE + 100), *self.matches_edit()),
                            self.line("section_matches", "backend/app/pricing.py:5", twins, total=14))

    def test_subagent_edits_count_only_after_the_turn_opened(self):
        transcript = self.root / ".claude" / "history.jsonl"
        subagents = transcript.with_suffix("") / "subagents"
        self.transcript(self.user(BASE + 60, "子任务"), *self.matches_edit(), path=subagents / "agent-a.jsonl")
        old = "def section_canonical(value):\n    return value\n"
        self.write("backend/app/old.py", old)
        self.transcript(*self.claude_call("Write", {"file_path": str(self.root / "backend/app/old.py"), "content": old},
                                          BASE - 1000, BASE - 900),
                        path=subagents / "agent-b.jsonl", mtime=BASE - 500)
        self.assert_context(self.stop(self.user(BASE + 50)),
                            self.line("section_matches", "backend/app/pricing.py:5"))

    def test_core_judgment_table_with_concepts_adds_the_pointer(self):
        self.write("docs/rules/core-judgments.md", "# 核心判断\n\n说明。\n")
        expected = self.line("section_matches", "backend/app/pricing.py:5")
        self.assert_context(self.stop(self.user(BASE + 100), *self.matches_edit()), expected)
        self.write("docs/rules/core-judgments.md", "# 核心判断\n\n## 同区\n- 定义:x\n")
        self.assert_context(self.stop(self.user(BASE + 100), *self.matches_edit()),
                            expected + "先对照 docs/rules/core-judgments.md。")

    def test_at_most_three_functions_are_named(self):
        names = ["section_key", "section_alias", "same_section_label", "section_canon"]
        text = "".join(f"\n\ndef {name}(value):\n    return value\n" for name in names)
        self.write("backend/app/pricing.py", EXISTING["backend/app/pricing.py"] + text)
        rows = self.edit("backend/app/pricing.py", "    return rows\n", "    return rows\n" + text)
        output = json.loads(self.stop(self.user(BASE + 100), *rows))
        lines = output["hookSpecificOutput"]["additionalContext"].splitlines()
        self.assertEqual([line.split("本轮新写的 ")[1].split("(")[0] for line in lines], names[:3])


class DefinitionPatternTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "judgment_twins", REPO / ".claude" / "hooks" / "judgment_twins.py")
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def names(self, text, suffix):
        return [name for _, name in self.module.definitions(text, suffix)]

    def test_script_definitions(self):
        text = "\n".join([
            "export default async function sectionKey<T>(value: T) {",
            "const sameSection = (left, right) => left === right;",
            "export const isSameSection = async (a: string, b = f(1)): Promise<boolean> => true;",
            "let sectionAlias = value => value;",
            "module.exports.matchSection = function (value) {",
            "const normalizeSection = (",
            "  static async canonicalSection(value: string): string {",
            "  if (sectionKey(a)) {",
            "  doThing(value, () => {",
            "type SectionKey = (value: string) => string;",
            "const total = (a + b) * 2;",
            "var sectionKeyMinified = function (a) {" + "a:b," * 200,
        ])
        self.assertEqual(self.names(text, ".ts"), [
            "sectionKey", "sameSection", "isSameSection", "sectionAlias", "matchSection",
            "normalizeSection", "canonicalSection",
        ])

    def test_python_definitions_and_name_words(self):
        text = "def section_identity(value):\n    async def _same_section(self, other):\n# def section_key(\nx = (\n"
        self.assertEqual(self.names(text, ".py"), ["section_identity", "_same_section"])
        self.assertEqual(self.module.judgment_nouns("isSameSection"), {"section"})
        self.assertEqual(self.module.judgment_nouns("_market_section_key"), {"market", "section"})
        self.assertEqual(self.module.judgment_nouns("_section_alias_match_key"), {"section"})
        self.assertEqual(self.module.judgment_nouns("get_value_key"), set())
        self.assertEqual(self.module.judgment_nouns("section_rows"), set())
        # Led by an action verb or test: the name does something, it does not decide sameness.
        for name in ("parseHTTPKey", "list_agent_keys", "saveManualMatch", "confirm_inventory_match",
                     "onKeyDown", "testSameSection"):
            self.assertEqual(self.module.judgment_nouns(name), set(), name)
        # A key that is only a credential, keyboard or storage key; another judgment word keeps it.
        for name in ("token_key", "keyDown", "_timestamp_sort_key", "_mail_cache_key"):
            self.assertEqual(self.module.judgment_nouns(name), set(), name)
        self.assertEqual(self.module.judgment_nouns("same_api_key"), {"api"})


if __name__ == "__main__":
    unittest.main()
