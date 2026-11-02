"""Real DSH Claude Code bridge with an offline ctx and isolated synthetic state."""

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

try:
    from compression import zstd
except ImportError:
    zstd = None


REPO = Path(__file__).resolve().parents[1]
BRIDGE = Path(os.environ.get(
    "DSH_BRIDGE_MODULE",
    str(Path.home() / ".dsh/profiles/desktop/node_modules/@deepseek-ai/dsh-hooks-claude-code/lib/index.js"),
))
SIM = REPO / "dsh/bridge_sim.mjs"
DISPATCH = REPO / "dsh/cc_hooks.py"
SESSION = "session-11111111-2222-4333-8444-555555555555"
CHILD = "11111111-2222-4333-8444-666666666666"


@unittest.skipUnless(BRIDGE.is_file() and shutil.which("node"), "installed DSH bridge and node required")
class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / ".git").mkdir()
        self.config = self.root / "bridge-hooks.json"
        self.env = {**os.environ, "HOME": str(self.home), "PYTHONDONTWRITEBYTECODE": "1"}

    def save(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def hook_config(self, hooks):
        self.save(self.config, {"hooks": {event: [{"hooks": [
            {"type": "command", "command": command} for command in commands
        ]}] for event, commands in hooks.items()}})

    def simulate(self, events):
        request = {"bridge": str(BRIDGE), "config": str(self.config),
                   "workspace": str(self.project), "events": events}
        run = subprocess.run(
            ["node", str(SIM)], input=json.dumps(request), text=True,
            capture_output=True, cwd=self.project, env=self.env, timeout=20,
        )
        self.assertEqual((run.returncode, run.stderr), (0, ""))
        return json.loads(run.stdout)["events"]

    def dispatcher_config(self):
        command = shlex.quote(sys.executable) + " " + shlex.quote(str(DISPATCH))
        self.hook_config({"SessionStart": [command], "UserPromptSubmit": [command], "Stop": [command]})

    def log(self, *, child=False, turn=1):
        if zstd is None:
            self.skipTest("v4 zstd needs Python 3.14")
        session_id = CHILD if child else SESSION
        rows = [{"type": "session", "version": 4, "id": session_id,
                 "cwd": str(self.project), "parentSession": SESSION if child else None}]
        rows += [{"type": "turn/start", "seq": number, "time": 1900000000000 + number,
                  "data": {"turn": number}} for number in range(1, turn + 1)]
        path = self.home / ".dsh/sessions/bucket" / session_id / "session.v4.jsonl.zstd"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(zstd.compress(("\n".join(map(json.dumps, rows)) + "\n").encode()))

    def trust(self, accepted=True):
        self.save(self.home / ".claude.json", {"projects": {
            str(self.project): {"hasTrustDialogAccepted": accepted}
        }})

    def install_harness(self):
        hooks = self.project / ".claude/hooks"
        hooks.mkdir(parents=True)
        for name in ("session_start.py", "stop_guard.py", "stop_evidence.py", "judgment_twins.py", "dictionary_updates.py"):
            shutil.copyfile(REPO / ".claude/hooks" / name, hooks / name)
        (self.project / ".scratch").mkdir()
        self.save(self.project / ".claude/settings.json", {"hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command":
                'python3 "${CLAUDE_PROJECT_DIR}/.claude/hooks/session_start.py"'}]}],
            "Stop": [{"hooks": [{"type": "command", "command":
                'python3 "${CLAUDE_PROJECT_DIR}/.claude/hooks/stop_guard.py"'}]}],
        }})

    def test_real_bridge_only_delivers_structured_session_context(self):
        plain = "printf 'PLAIN-CONTEXT\\n'"
        structured = "printf '%s\\n' '{\"hookSpecificOutput\":{\"hookEventName\":\"SessionStart\",\"additionalContext\":\"JSON-CONTEXT\"}}'"
        self.hook_config({"SessionStart": [plain, structured]})
        result = self.simulate([{"kind": "start", "id": SESSION}])[0]
        self.assertEqual(result["contexts"], ["JSON-CONTEXT"])
        self.assertEqual(result["runCount"], 2)

    @unittest.skipIf(zstd is None, "v4 zstd needs Python 3.14")
    def test_dispatcher_harness_context_stop_cap_and_next_turn(self):
        self.trust()
        self.log(turn=0)
        self.install_harness()
        settings = self.project / ".claude/settings.json"
        config = json.loads(settings.read_text(encoding="utf-8"))
        config["hooks"]["SessionStart"][0]["hooks"] += [
            {"type": "command", "command": "printf 'PLAIN-CONTEXT\\n'"},
            {"type": "command", "command": "printf '%s\\n' '{\"hookSpecificOutput\":{\"hookEventName\":\"SessionStart\",\"additionalContext\":\"JSON-CONTEXT\"}}'"},
        ]
        self.save(settings, config)
        self.dispatcher_config()
        task = self.project / ".scratch/example"
        task.mkdir()
        (task / "spec.md").write_text(
            "Status: in-progress\n会话: " + SESSION + "\n\n## 验收\n"
            "- [ ] [我] finish\n\n## 进展\n"
            "- 10-25 09:00 done: started | next: 我: finish\n", encoding="utf-8")
        opening = self.simulate([
            {"kind": "start", "id": SESSION},
            {"kind": "prompt", "id": SESSION, "text": "user"},
        ])
        self.assertIn("example", "".join(opening[0]["contexts"]))
        self.assertIn("PLAIN-CONTEXT", "".join(opening[0]["contexts"]))
        self.assertIn("JSON-CONTEXT", "".join(opening[0]["contexts"]))
        self.assertLess(opening[0]["totalMs"] - opening[0]["hookMs"], 1000)

        # DSH may persist turn/start after the prompt callback has returned.
        self.log(turn=1)
        first_turn = self.simulate([
            {"kind": "stop", "id": SESSION, "turn": 1},
            {"kind": "prompt", "id": SESSION, "text": "steered continuation"},
            {"kind": "stop", "id": SESSION, "turn": 1},
        ])
        self.assertEqual(len(first_turn[0]["contexts"]), 1)
        self.assertIn("example", first_turn[0]["contexts"][0])
        self.assertEqual(first_turn[2]["contexts"], [])

        # A later prompt alone cannot distinguish a new user turn from a steer.
        before_flush = self.simulate([{"kind": "prompt", "id": SESSION, "turn": 2},
                                      {"kind": "stop", "id": SESSION, "turn": 2}])
        self.assertEqual(before_flush[1]["contexts"], [])
        self.log(turn=2)
        later = self.simulate([{"kind": "stop", "id": SESSION, "turn": 2}])
        self.assertEqual(len(later[0]["contexts"]), 1)

    @unittest.skipIf(zstd is None, "v4 zstd needs Python 3.14")
    def test_no_harness_untrusted_and_child_do_not_block(self):
        self.log()
        self.dispatcher_config()
        self.trust()
        bare = self.simulate([{"kind": "start", "id": SESSION},
                              {"kind": "stop", "id": SESSION}])
        self.assertEqual([event["contexts"] for event in bare], [[], []])
        self.assertLess(bare[0]["totalMs"], 1000)

        marker = self.root / "untrusted-ran"
        code = "from pathlib import Path; Path(" + repr(str(marker)) + ").write_text('bad'); print('{\"decision\":\"block\",\"reason\":\"bad\"}')"
        command = shlex.quote(sys.executable) + " -c " + shlex.quote(code)
        self.save(self.project / ".claude/settings.json", {"hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": command}]}]}})
        self.trust(False)
        untrusted = self.simulate([{"kind": "stop", "id": SESSION}])
        self.assertEqual(untrusted[0]["contexts"], [])
        self.assertFalse(marker.exists())

        self.trust()
        self.log(child=True)
        child = self.simulate([{"kind": "prompt", "id": CHILD},
                               {"kind": "stop", "id": CHILD}])
        self.assertEqual(child[1]["contexts"], [])


if __name__ == "__main__":
    unittest.main()
