import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INIT = ROOT / "init.py"


def run(*args):
    return subprocess.run([sys.executable, str(INIT), *args], capture_output=True, text=True)


class InitProjectTest(unittest.TestCase):
    def test_fresh_dir_gets_all_pieces(self):
        with tempfile.TemporaryDirectory() as d:
            r = run(d)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            t = Path(d)
            self.assertTrue((t / "AGENTS.md").is_file())
            self.assertEqual(os.readlink(t / "CLAUDE.md"), "AGENTS.md")
            self.assertTrue((t / "docs" / "rules" / "harness.md").is_file())
            self.assertTrue((t / "docs" / "decisions.md").is_file())
            self.assertTrue((t / ".scratch" / ".gitkeep").is_file())
            self.assertTrue((t / ".claude" / "hooks" / "stop_guard.py").is_file())
            self.assertTrue((t / ".codex" / "hooks").is_symlink())
            self.assertTrue((t / ".codex" / "hooks" / "session_start.py").is_file())
            self.assertTrue((t / ".agents" / "skills" / "interview-me" / "SKILL.md").is_file())
            self.assertTrue((t / ".claude" / "skills" / "interview-me").is_symlink())
            self.assertTrue((t / ".claude" / "skills" / "interview-me" / "SKILL.md").is_file())
            for cfg, prefix in ((t / ".claude" / "settings.json", '"$CLAUDE_PROJECT_DIR"/.claude/hooks'),
                                (t / ".codex" / "hooks.json", ".codex/hooks")):
                data = json.loads(cfg.read_text())
                cmds = [h["command"] for ev in ("SessionStart", "Stop")
                        for g in data["hooks"][ev] for h in g["hooks"]]
                self.assertEqual(len(cmds), 2)
                self.assertTrue(all(prefix in c for c in cmds), cmds)
            self.assertIn(".scratch/.session", (t / ".gitignore").read_text())
            self.assertIn("/hooks", r.stdout)

    def test_rerun_is_idempotent_and_keeps_edited_agents_md(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(run(d).returncode, 0)
            t = Path(d)
            (t / "AGENTS.md").write_text("# 我的规则\n")
            before = {p: p.stat().st_mtime_ns for p in t.rglob("*") if p.is_file()}
            r = run(d)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertEqual((t / "AGENTS.md").read_text(), "# 我的规则\n")
            after = {p: p.stat().st_mtime_ns for p in t.rglob("*") if p.is_file()}
            changed = [p for p in before if before[p] != after.get(p)]
            self.assertEqual(changed, [], changed)
            self.assertIn("路由表里要有一行", r.stdout)

    def test_conflict_refuses_before_writing_anything(self):
        with tempfile.TemporaryDirectory() as d:
            t = Path(d)
            (t / ".claude" / "hooks").mkdir(parents=True)
            (t / ".claude" / "hooks" / "stop_guard.py").write_text("print('mine')\n")
            r = run(d)
            self.assertEqual(r.returncode, 1)
            self.assertIn("冲突", r.stdout)
            self.assertIn("stop_guard.py", r.stdout)
            self.assertFalse((t / "AGENTS.md").exists())
            self.assertFalse((t / ".scratch").exists())
            self.assertFalse((t / ".codex").exists())

    def test_wrong_symlink_target_is_a_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            t = Path(d)
            (t / "AGENTS.md").write_text("x")
            (t / "CLAUDE.md").symlink_to("README.md")
            r = run(d)
            self.assertEqual(r.returncode, 1)
            self.assertIn("CLAUDE.md", r.stdout)
            self.assertFalse((t / "docs").exists())

    def test_merges_into_existing_settings_without_dropping_keys(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / ".claude" / "settings.json"
            cfg.parent.mkdir()
            cfg.write_text(json.dumps({"permissions": {"allow": ["Bash(ls:*)"]},
                                       "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo hi"}]}]}}))
            self.assertEqual(run(d).returncode, 0)
            data = json.loads(cfg.read_text())
            self.assertEqual(data["permissions"], {"allow": ["Bash(ls:*)"]})
            stop_cmds = [h["command"] for g in data["hooks"]["Stop"] for h in g["hooks"]]
            self.assertEqual(stop_cmds[0], "echo hi")
            self.assertEqual(len(stop_cmds), 2)
            self.assertEqual(run(d).returncode, 0)
            self.assertEqual(len([h for g in json.loads(cfg.read_text())["hooks"]["Stop"] for h in g["hooks"]]), 2)

    def test_bad_json_config_is_a_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / ".codex" / "hooks.json"
            cfg.parent.mkdir()
            cfg.write_text("{not json")
            r = run(d)
            self.assertEqual(r.returncode, 1)
            self.assertIn("hooks.json", r.stdout)
            self.assertFalse((Path(d) / "AGENTS.md").exists())


if __name__ == "__main__":
    unittest.main()


class CodexTrustHashTest(unittest.TestCase):
    def test_reproduces_known_codex_trust_hash(self):
        # 对照向量:owner 机器上 Codex /hooks 为 {"type":"command","command":<cmd>,"timeout":5} 写下的 trusted_hash
        sys.path.insert(0, str(ROOT))
        import init
        with tempfile.TemporaryDirectory() as d:
            hj = Path(d) / "hooks.json"
            hj.write_text(json.dumps({"hooks": {"SessionStart": [{"hooks": [
                {"type": "command", "command": "/Users/sangba/.codeisland/codeisland-bridge --source codex", "timeout": 5}]}]}}))
            entries = init.codex_trust_entries(hj)
            self.assertEqual(entries[0][0], f"{hj}:session_start:0:0")
            self.assertEqual(entries[0][1], "sha256:a8afc32db558e2dbc9583c320392ce307f02e9c3d4b987b5021fd59d645d94bf")

    def test_init_prints_trust_entries(self):
        with tempfile.TemporaryDirectory() as d:
            r = run(d)
            self.assertEqual(r.returncode, 0)
            self.assertIn("hooks.state", r.stdout)
            self.assertEqual(r.stdout.count("trusted_hash"), 2)

