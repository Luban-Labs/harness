"""DSH session identity and board state from verified dispatcher records."""

import json
import os
import runpy
import time
from unittest.mock import patch

from hook_support import HookCase, SESSION_START


hook = runpy.run_path(str(SESSION_START))
session_matches = hook["session_matches"]


class DshSessionTest(HookCase):
    FIRST = "session-12345678-1111-2222-3333-444444444444"
    COLLISION = "session-12345678-aaaa-bbbb-cccc-dddddddddddd"
    SECOND = "session-87654321-1111-2222-3333-444444444444"
    CHILD = "aaaaaaaa-1111-2222-3333-444444444444"

    def task(self, name, claim, progress=""):
        folder = self.root / ".scratch" / name
        folder.mkdir()
        (folder / "spec.md").write_text(
            f"Status: in-progress\n会话: {claim}\n\n## 进展\n{progress}",
            encoding="utf-8",
        )

    def context(self, session=None, **extra):
        with patch.dict(os.environ, {"HARNESS_HOST": "dsh"}):
            output = self.run_session({
                "cwd": str(self.root), "session_id": session or self.FIRST,
                "dsh_parent_session_id": None, "dsh_session_records": [], **extra,
            })
        return json.loads(output)["hookSpecificOutput"]["additionalContext"]

    def test_top_level_short_ids_keep_uuid_and_claims_do_not_collapse(self):
        with patch.dict(os.environ, {"HARNESS_HOST": ""}):
            self.assertFalse(session_matches("session-", self.FIRST))
            self.assertTrue(session_matches("session-", "session-garbage"))
        with patch.dict(os.environ, {"HARNESS_HOST": "dsh"}):
            self.assertTrue(session_matches(self.FIRST[:16], self.FIRST))
            self.assertFalse(session_matches("session-", self.FIRST))
            self.assertFalse(session_matches(self.FIRST[8:16], self.FIRST))
            self.assertFalse(session_matches(self.FIRST[:16], self.SECOND))
            self.assertFalse(session_matches(self.FIRST[:16], self.CHILD))
        self.task("first", self.FIRST[:16])
        self.task("second", self.SECOND[:16])
        context = self.context()
        self.assertIn("本会话认领: first", context)
        self.assertNotIn("本会话认领: second", context)
        self.assertIn("first · 会话 session-12345678 ·", context)
        self.assertIn("second · 会话 session-87654321 ·", context)
        self.assertNotIn("会话 session- ·", context)

    def test_cc_board_displays_distinct_dsh_claims(self):
        self.task("first", self.FIRST)
        self.task("second", self.SECOND[:16])
        with patch.dict(os.environ, {"HARNESS_HOST": ""}):
            output = self.run_session({"cwd": str(self.root), "session_id": self.CHILD})
        context = json.loads(output)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("first · 会话 session-12345678 ·", context)
        self.assertIn("second · 会话 session-87654321 ·", context)
        self.assertNotIn("本会话认领:", context)

    def test_takeover_uses_qualified_short_id(self):
        self.task("taken", self.SECOND, "- done: 接手自 session-12345678\n")
        self.assertIn("已被会话 session-87654321 接手", self.context())
        self.assertNotIn("你认领过", self.context(self.CHILD))
        self.assertNotIn("你认领过", self.context(self.FIRST, dsh_parent_session_id="parent"))
        self.task("legacy", self.SECOND, "- done: 接手自 session-\n")
        self.task("wrong-prefix", self.SECOND, "- done: 接手自 session-12345678x\n")
        self.assertNotIn("你认领过的 Task legacy", self.context())
        self.assertNotIn("你认领过的 Task wrong-prefix", self.context())

    def test_bare_uuid_child_marker_does_not_claim_task(self):
        self.task("legacy", self.CHILD)
        context = self.context(self.CHILD, dsh_parent_session_id=self.FIRST)
        self.assertNotIn("本会话认领:", context)

    def test_verified_top_level_record_mtime_controls_dsh_board_state(self):
        self.task("recent", self.FIRST)
        self.task("old", self.SECOND)
        self.task("missing", "session-ffffffff-1111-2222-3333-444444444444")
        context = self.context(dsh_session_records=[
            {"session_id": self.FIRST, "mtime": time.time() - 2 * 3600,
             "parent_session_id": None},
            {"session_id": self.SECOND, "mtime": time.time() - 11 * 3600,
             "parent_session_id": None},
            {"session_id": self.CHILD, "mtime": time.time(),
             "parent_session_id": self.FIRST},
        ])
        self.assertIn("recent · 会话 session-12345678(在做)", context)
        self.assertIn("old · 会话 session-87654321(断了 11 小时)", context)
        self.assertIn("missing · 会话 session-ffffffff ·", context)

    def test_legacy_prefix_and_colliding_records_are_unknown(self):
        self.task("legacy-host", "session-")
        self.task("legacy-bare", "12345678")
        self.task("collision", self.FIRST[:16])
        context = self.context(dsh_session_records=[
            {"session_id": self.FIRST, "mtime": time.time() - 2 * 3600,
             "parent_session_id": None},
            {"session_id": self.COLLISION, "mtime": time.time() - 12 * 3600,
             "parent_session_id": None},
        ])
        self.assertNotIn("本会话认领: legacy-host", context)
        self.assertNotIn("本会话认领: legacy-bare", context)
        self.assertIn("collision · 会话 session-12345678 ·", context)

    def test_dsh_record_index_is_shared_and_obeys_deadline(self):
        class CountedRows(list):
            scans = 0

            def __iter__(self):
                self.scans += 1
                return super().__iter__()

        rows = CountedRows([
            {"session_id": self.FIRST, "mtime": time.time(), "parent_session_id": None},
            {"session_id": self.SECOND, "mtime": time.time(), "parent_session_id": None},
        ])
        probe = {"home": None, "deadline": time.monotonic() + 1,
                 "indexes": {}, "dsh_session_records": rows}
        self.assertIsNotNone(hook["record_stamp"](self.FIRST[:16], "dsh", probe))
        self.assertIsNotNone(hook["record_stamp"](self.SECOND[:16], "dsh", probe))
        self.assertEqual(rows.scans, 1)
        probe["deadline"] = time.monotonic() - 1
        self.assertIsNone(hook["record_stamp"](self.FIRST[:16], "dsh", probe))

    def test_main_worktree_helper_keeps_task_scratch_gate(self):
        main = self.root / "main"
        linked = self.root / "linked"
        gitdir = main / ".git/worktrees/linked"
        gitdir.mkdir(parents=True)
        (linked / ".scratch").mkdir(parents=True)
        marker = linked / ".git"
        marker.write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
        (gitdir / "gitdir").write_text(str(marker) + "\n", encoding="utf-8")
        (gitdir / "commondir").write_text("../..\n", encoding="utf-8")
        self.assertEqual(hook["main_worktree"](linked), main.resolve())
        self.assertEqual(hook["project_roots"](linked), (linked.resolve(), linked.resolve()))
        (main / ".scratch").mkdir()
        self.assertEqual(hook["project_roots"](linked), (linked.resolve(), main.resolve()))
        (gitdir / "gitdir").write_text(str(main / ".git") + "\n", encoding="utf-8")
        self.assertIsNone(hook["main_worktree"](linked))
