#!/usr/bin/env python3
"""Create a synthetic Trellis project for migration tests.

Usage: python3 tests/trellis_fixture.py <empty-directory>
"""

import json
import sys
from pathlib import Path


def write(root, relative, content):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def write_json(root, relative, value):
    return write(
        root,
        relative,
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
    )


def task(root, relative, status, title=None, files=()):
    base = Path(".trellis/tasks") / relative
    metadata = {"status": status}
    if title is not None:
        metadata["title"] = title
    write_json(root, base / "task.json", metadata)
    for name, content in files:
        write(root, base / name, content)


def build_fixture(root):
    root = Path(root)
    if not root.is_dir() or any(root.iterdir()):
        raise ValueError("target must be an existing empty directory")

    task(
        root,
        "plan-next",
        "planning",
        "Plan the next release",
        (
            ("prd.md", "# Requirements\nacceptance stays synthetic\n"),
            ("design-api.md", "# Design\nstdlib only\n"),
            ("implementation.md", "# Steps\nship one slice\n"),
            ("research/notes.md", "# Research\nfixture evidence\n"),
            ("dispatch/worker.md", "# Dispatch\nsynthetic packet\n"),
            ("协作单-示例.md", "# 协作单\n汇合点:tests\n"),
            ("context.jsonl", '{"kind":"synthetic"}\n'),
            ("assets/payload.bin", b"\x00synthetic-trellis\xff"),
            ("notes.txt", "keep this note byte-for-byte\n"),
        ),
    )
    task(
        root,
        "active-build",
        "in_progress",
        "Active build",
        (("prd.md", "# Active requirements\n"),),
    )
    task(
        root,
        "active-review",
        "in_progress",
        "Active review",
        (("design.md", "# Review design\n"),),
    )
    task(
        root,
        "archive/2026-08/completed-one",
        "completed",
        None,
        (("result.md", "# Result\nalready complete\n"),),
    )
    task(
        root,
        "00-bootstrap-guidelines",
        "planning",
        "Bootstrap guidelines",
        (("workflow.md", "# Old bootstrap workflow\n"),),
    )

    write(root, ".trellis/templates/task.md", "How to Fill\nDo not promote me.\n")
    write(root, ".trellis/spec/project.md", "# Synthetic project specification\n")
    write_json(root, ".trellis/workspace/state.json", {"phase": "synthetic"})
    write(root, ".trellis/workflow.md", "# Legacy workflow\n")
    write(root, ".trellis/agents/reviewer.md", "# Legacy agent\n")
    write(root, ".trellis/scripts/check.py", "print('legacy')\n")
    write(root, ".trellis/config.yaml", "enabled: true\n")
    write(root, ".trellis/extras/opaque.dat", b"opaque\x00data")

    write(root, ".claude/hooks/session-start.py", "# legacy session start\n")
    write(root, ".claude/hooks/trellis_guard.py", "# named trellis hook\n")
    write(root, ".claude/hooks/custom.py", "# unrelated hook must stay\n")
    write(root, ".claude/agents/trellis-reviewer.md", "# legacy reviewer\n")
    write(root, ".claude/commands/open-trellis.md", "# legacy command\n")
    write(root, ".claude/skills/trellis-flow/SKILL.md", "# legacy skill\n")
    write(root, ".agents/skills/my-trellis-helper/SKILL.md", "# legacy shared skill\n")
    write(root, ".codex/agents/trellis-worker.md", "# legacy codex agent\n")
    for name in (
        "session-start.py",
        "inject-workflow-state.py",
        "inject-subagent-context.py",
    ):
        write(root, f".codex/hooks/{name}", f"# old Codex hook {name}\n")
    write(root, ".dsh/skills/trellis-runtime/SKILL.md", "# legacy DSH skill\n")

    write_json(
        root,
        ".claude/settings.json",
        {
            "env": {"KEEP_ME": "yes"},
            "enabledPlugins": {"fixture@example": True},
            "hooks": {
                "SessionStart": [
                    {
                        "matcher": "startup",
                        "groupMeta": "keep",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 .claude/hooks/session-start.py",
                                "timeout": 7,
                            },
                            {
                                "type": "command",
                                "command": "python3 .claude/hooks/custom.py",
                                "timeout": 8,
                            },
                        ],
                    }
                ],
                "Stop": [
                    {
                        "matcher": "stop",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 .claude/hooks/inject-workflow-state.py",
                            }
                        ],
                    }
                ],
                "Notification": [
                    {
                        "hooks": [
                            {"type": "command", "command": "python3 notify.py"}
                        ]
                    }
                ],
                "LegacyOnly": [
                    {
                        "matcher": "legacy",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 .claude/hooks/inject-subagent-context.py",
                            }
                        ],
                    }
                ],
            },
            "unrelated": [1, 2, 3],
        },
    )
    write_json(
        root,
        ".codex/hooks.json",
        {
            "keep": {"nested": True},
            "hooks": {
                "SessionStart": [
                    {
                        "matcher": "startup",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 .codex/hooks/inject-subagent-context.py",
                            }
                        ],
                    }
                ],
                "Stop": [
                    {
                        "hooks": [
                            {"type": "command", "command": "python3 keep-stop.py"}
                        ]
                    }
                ],
            },
        },
    )
    write(
        root,
        ".codex/config.toml",
        "# Generated by Trellis\n"
        'project_doc_fallback_filenames = ["TRELLIS.md"]\n'
        "[agents]\n"
        "max_depth = 1\n"
        "# treLLis compatibility comment\n",
    )
    write(
        root,
        "AGENTS.md",
        "# Existing project rules\n\n"
        "Keep this owner rule.\n\n"
        "<!-- TRELLIS:START -->\n"
        "Legacy Trellis injected instructions.\n"
        "<!-- TRELLIS:END -->\n\n"
        "Manual Trellis note points at .trellis/manual.md and must be reviewed.\n",
    )
    write(root, ".gitattributes", "*.txt text\n.trellis/** linguist-vendored\n*.bin binary\n")
    write(root, ".gitignore", "dist/")
    write(root, "docs/decisions.md", "# Owner decisions\n\nPreserve exactly.\n")
    write(root, "src/keep.py", "VALUE = 'unknown files stay'\n")
    write(root, ".claude/commands/custom.md", "# Unrelated command stays\n")


def main(argv):
    if len(argv) != 1:
        print(__doc__.strip())
        return 1
    try:
        build_fixture(Path(argv[0]))
    except (OSError, ValueError) as error:
        print(f"fixture error: {error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
