#!/usr/bin/env python3
"""给一个项目装 harness。用法:python3 init.py <目标目录> [--no-skill]

先全量预检,任何冲突就一个字节都不写、退出 1;重复跑是安全的(已装好的部分原样保留)。
装的东西:
  AGENTS.md(来自 templates/AGENTS.md;已有就保留,提示手动加路由行)+ CLAUDE.md 符号链接
  docs/rules/harness.md(复制)、docs/decisions.md(空账本)、.scratch/.gitkeep
  两个 hook 脚本复制到 .claude/hooks/,.codex/hooks 做符号链接指过去
  .claude/settings.json 与 .codex/hooks.json 追加 SessionStart / Stop 两条 hook,
  Claude 用 "$CLAUDE_PROJECT_DIR"/.claude/hooks/…,Codex 用 .codex/hooks/…(从项目根启动);已有配置只追加不改其他键
  .gitignore 追加 .scratch/.session
  interview-me skill 复制到 .agents/skills/(Codex 扫这里),.claude/skills/interview-me 做符号链接(Claude 扫这里);--no-skill 跳过
冲突的定义:同名文件已存在且内容不同,或该位置类型不对(该是链接的不是链接、链接指错)。处理冲突要人看 diff 后自己删,init 不覆盖。
Codex 的 hook 要先被信任:init 会按 Codex 的算法算出两条信任条目并打印,追加到 ~/.codex/config.toml 即可;
或者在目标目录进 codex 交互界面跑一次 /hooks。
"""

import filecmp
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
HOOKS = ("session_start.py", "stop_guard.py", "stop_evidence.py")
SKILL = "interview-me"
LEDGER = "# 决策账本\n\n给人看的。不进路由表、不进任何注入;只追加。每条:背景、决定、为什么。\n"
GITIGNORE_LINE = ".scratch/.session"


def hook_entries(prefix):
    return {
        "SessionStart": [{"hooks": [{"type": "command", "timeout": 10,
                                     "command": f"python3 {prefix}/{HOOKS[0]}"}]}],
        "Stop": [{"hooks": [{"type": "command", "timeout": 10,
                             "command": f"python3 {prefix}/{HOOKS[1]}"}]}],
    }


def missing_hooks(path, prefix):
    """返回还没登记的 (event, groups);全部已登记则为空。"""
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    hooks = data.get("hooks", {})
    out = []
    for event, groups in hook_entries(prefix).items():
        wanted = groups[0]["hooks"][0]["command"]
        if not any(h.get("command") == wanted for g in hooks.get(event, []) for h in g.get("hooks", [])):
            out.append((event, groups))
    return out


EVENT_KEY = {"SessionStart": "session_start", "Stop": "stop"}


def codex_trust_entries(hooks_json_path):
    """复现 Codex(rust-v0.153.4)hook_hash:归一化定义 → 规范 JSON → sha256。"""
    data = json.loads(Path(hooks_json_path).read_text(encoding="utf-8"))
    out = []
    for event, groups in data.get("hooks", {}).items():
        for gi, group in enumerate(groups):
            for hi, hd in enumerate(group.get("hooks", [])):
                handler = {"async": hd.get("async", False), "command": hd["command"],
                           "type": hd.get("type", "command")}
                if "timeout" in hd:
                    handler["timeout"] = hd["timeout"]
                ident = {"event_name": EVENT_KEY.get(event, event), "hooks": [handler]}
                if group.get("matcher") is not None:
                    ident["matcher"] = group["matcher"]
                canonical = json.dumps(ident, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                out.append((f"{hooks_json_path}:{EVENT_KEY.get(event, event)}:{gi}:{hi}", f"sha256:{digest}"))
    return out


def merge_hooks(path, prefix):
    todo = missing_hooks(path, prefix)
    if not todo:
        return path
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    hooks = data.setdefault("hooks", {})
    for event, groups in todo:
        hooks.setdefault(event, []).extend(groups)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def same_tree(a, b):
    cmp = filecmp.dircmp(a, b)
    if cmp.left_only or cmp.right_only or cmp.diff_files or cmp.funny_files:
        return False
    return all(same_tree(Path(a) / d, Path(b) / d) for d in cmp.common_dirs)


class Plan:
    def __init__(self, target):
        self.t = target
        self.actions, self.conflicts, self.kept, self.notes = [], [], [], []

    def copy(self, src, rel):
        dst = self.t / rel
        if dst.is_symlink() or dst.exists():
            if dst.is_file() and not dst.is_symlink() and filecmp.cmp(src, dst, shallow=False):
                self.kept.append(rel)
            else:
                self.conflicts.append(f"{rel} 已存在且内容不同或类型不对")
            return
        self.actions.append((rel, lambda: (dst.parent.mkdir(parents=True, exist_ok=True), shutil.copy(src, dst))))

    def link(self, rel, to):
        dst = self.t / rel
        if dst.is_symlink():
            if os.readlink(dst) == to:
                self.kept.append(f"{rel} -> {to}")
            else:
                self.conflicts.append(f"{rel} 已是符号链接但指向 {os.readlink(dst)},应为 {to}")
        elif dst.exists():
            self.conflicts.append(f"{rel} 已存在且不是符号链接")
        else:
            self.actions.append((f"{rel} -> {to}", lambda: (dst.parent.mkdir(parents=True, exist_ok=True), dst.symlink_to(to))))

    def write_if_missing(self, rel, text):
        dst = self.t / rel
        if dst.exists() or dst.is_symlink():
            self.kept.append(rel)
        else:
            self.actions.append((rel, lambda: (dst.parent.mkdir(parents=True, exist_ok=True), dst.write_text(text, encoding="utf-8"))))

    def copytree(self, src, rel):
        dst = self.t / rel
        if dst.is_symlink() or dst.exists():
            if dst.is_dir() and not dst.is_symlink() and same_tree(src, dst):
                self.kept.append(rel + "/")
            else:
                self.conflicts.append(f"{rel}/ 已存在且内容不同或类型不对")
            return
        self.actions.append((rel + "/", lambda: shutil.copytree(src, dst)))

    def config(self, rel, prefix):
        dst = self.t / rel
        if dst.is_symlink() or (dst.exists() and not dst.is_file()):
            self.conflicts.append(f"{rel} 类型不对")
            return
        if dst.is_file():
            try:
                json.loads(dst.read_text(encoding="utf-8"))
            except ValueError:
                self.conflicts.append(f"{rel} 不是合法 JSON")
                return
        if dst.is_file() and not missing_hooks(dst, prefix):
            self.kept.append(rel)
        else:
            self.actions.append((rel, lambda: merge_hooks(dst, prefix)))


def build_plan(target, with_skill):
    p = Plan(target)
    agents = target / "AGENTS.md"
    if agents.is_symlink() or (agents.exists() and not agents.is_file()):
        p.conflicts.append("AGENTS.md 类型不对")
    elif agents.exists():
        p.kept.append("AGENTS.md(保留你的;路由表里要有一行「开始做或收一个 Task → docs/rules/harness.md」)")
    else:
        p.copy(HARNESS / "templates" / "AGENTS.md", "AGENTS.md")
    p.link("CLAUDE.md", "AGENTS.md")
    p.copy(HARNESS / "docs" / "rules" / "harness.md", "docs/rules/harness.md")
    p.write_if_missing("docs/decisions.md", LEDGER)
    p.write_if_missing(".scratch/.gitkeep", "")
    for name in HOOKS:
        p.copy(HARNESS / ".claude" / "hooks" / name, f".claude/hooks/{name}")
    p.link(".codex/hooks", "../.claude/hooks")
    p.config(".claude/settings.json", '"$CLAUDE_PROJECT_DIR"/.claude/hooks')
    p.config(".codex/hooks.json", ".codex/hooks")
    gi = target / ".gitignore"
    if gi.is_symlink() or (gi.exists() and not gi.is_file()):
        p.conflicts.append(".gitignore 类型不对")
    elif not gi.exists() or GITIGNORE_LINE not in gi.read_text(encoding="utf-8").splitlines():
        def append():
            with gi.open("a", encoding="utf-8") as f:
                f.write(GITIGNORE_LINE + "\n")
        p.actions.append((f".gitignore(+{GITIGNORE_LINE})", append))
    else:
        p.kept.append(".gitignore")
    if with_skill:
        p.copytree(HARNESS / ".agents" / "skills" / SKILL, f".agents/skills/{SKILL}")
        p.link(f".claude/skills/{SKILL}", f"../../.agents/skills/{SKILL}")
    return p


def main(argv):
    args = [a for a in argv if not a.startswith("-")]
    flags = {a for a in argv if a.startswith("-")}
    if len(args) != 1 or flags & {"--help", "-h"}:
        print(__doc__)
        return 0 if flags & {"--help", "-h"} else 1
    target = Path(args[0]).resolve()
    if not target.is_dir():
        print(f"目标目录不存在:{target}")
        return 1
    plan = build_plan(target, "--no-skill" not in flags)
    if plan.conflicts:
        print(f"拒绝,未写入任何文件。{target} 里有 {len(plan.conflicts)} 处冲突:")
        for c in plan.conflicts:
            print(f"  ! {c}")
        return 1
    for label, fn in plan.actions:
        fn()
    print(f"{target}:")
    for label, _ in plan.actions:
        print(f"  + {label}")
    for k in plan.kept:
        print(f"  = {k}")
    print("Codex 侧还要信任这两条 hook。把下面追加到 ~/.codex/config.toml(或在该目录进 codex 跑一次 /hooks):")
    for key, digest in codex_trust_entries(target / ".codex" / "hooks.json"):
        print(f'[hooks.state."{key}"]\ntrusted_hash = "{digest}"')
    if not any(k.startswith("AGENTS.md") for k in plan.kept):
        print("然后打开 AGENTS.md 填全项目硬规则与路由表。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
