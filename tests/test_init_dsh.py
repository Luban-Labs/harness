"""Installer guidance uses the dispatcher's CC trust decision without home writes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class InitDshTest(unittest.TestCase):
    def install(self, trust):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            home, target = base / "home", base / "project"
            home.mkdir()
            target.mkdir()
            (target / ".git").mkdir()
            config = home / ".claude.json"
            config.write_text(trust(target), encoding="utf-8")
            before = {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()}
            result = subprocess.run(
                [sys.executable, str(ROOT / "init.py"), str(target)],
                capture_output=True, text=True, timeout=15,
                env={**os.environ, "HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1"},
            )
            self.assertEqual((result.returncode, result.stderr), (0, ""))
            after = {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()}
            self.assertEqual(before, after)
            self.assertIn("DSH:", result.stdout)
            return result.stdout

    def test_untrusted_target_warns_and_preserves_user_files(self):
        output = self.install(lambda target: json.dumps({"projects": {
            str(target): {"hasTrustDialogAccepted": False}}}))
        self.assertIn("尚未获 Claude Code 信任", output)

    def test_trusted_target_needs_no_warning(self):
        output = self.install(lambda target: json.dumps({"projects": {
            str(target): {"hasTrustDialogAccepted": True}}}))
        self.assertNotIn("尚未获 Claude Code 信任", output)

    def test_bad_trust_file_does_not_leak_or_abort_install(self):
        output = self.install(lambda target: "{synthetic-private-marker")
        self.assertIn("尚未获 Claude Code 信任", output)
        self.assertNotIn("synthetic-private-marker", output)
