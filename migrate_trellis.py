#!/usr/bin/env python3
"""Migrate a Trellis project to this repository's lightweight harness.

Usage:
  python3 migrate_trellis.py <root> [--apply]
      [--scope <task>=<dir> ...] [--date YYYY-MM-DD]

The default is a dry run.  The complete plan is built before any target file
is changed; every detected conflict therefore rejects the whole migration.
"""

import sys

# Importing init.py must not create a repository __pycache__ even when the
# caller did not set PYTHONDONTWRITEBYTECODE.
sys.dont_write_bytecode = True

import argparse
from dataclasses import dataclass
from datetime import date, datetime
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

import init


HARNESS = Path(__file__).resolve().parent
ARCHIVE = Path("docs/archive/trellis")
LEGACY_SCRIPTS = {
    "session-start.py",
    "inject-workflow-state.py",
    "inject-subagent-context.py",
}
PLATFORM_DIRS = (
    ".claude/hooks",
    ".claude/agents",
    ".claude/commands",
    ".claude/skills",
    ".agents/skills",
    ".codex/agents",
    ".codex/hooks",
    ".dsh/skills",
)
STATUS_DEST = {
    "planning": ("ready-for-agent", Path(".scratch")),
    "in_progress": ("in-progress", Path(".scratch")),
    "completed": ("done", Path(".scratch/archive")),
}
class CliError(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise CliError(message)


@dataclass
class Action:
    phase: int
    label: str
    run: object


class MigrationPlan:
    def __init__(self, root):
        self.root = root
        self.actions = []
        self.conflicts = []
        self.kept = []
        self.notes = []
        self._destinations = set()
        self._removed = set()

    def conflict(self, message):
        if message not in self.conflicts:
            self.conflicts.append(message)

    def keep(self, message):
        if message not in self.kept:
            self.kept.append(message)

    def _relative(self, path):
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return str(path)

    def _safe_parents(self, path):
        try:
            rel = path.relative_to(self.root)
        except ValueError:
            self.conflict(f"目标越出项目: {path}")
            return False
        current = self.root
        for part in rel.parts[:-1]:
            if part == ".git":
                self.conflict(f"拒绝访问 .git 路径: {self._relative(path)}")
                return False
            current = current / part
            if current.is_symlink():
                self.conflict(f"目标父路径是符号链接: {self._relative(current)}")
                return False
            if current.exists() and not current.is_dir():
                self.conflict(f"目标父路径不是目录: {self._relative(current)}")
                return False
        return True

    def reserve(self, path, description):
        key = str(path)
        if key in self._destinations:
            self.conflict(f"多个动作写入同一目标: {self._relative(path)} ({description})")
            return False
        self._destinations.add(key)
        return self._safe_parents(path)

    def mkdir(self, path, *, strict=False):
        if not self._safe_parents(path):
            return
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            self.conflict(f"目录目标类型冲突: {self._relative(path)}")
            return
        if path.is_dir():
            if strict:
                self.conflict(f"任务目标已存在: {self._relative(path)}")
            else:
                self.keep(self._relative(path) + "/")
            return
        if not self.reserve(path, "mkdir"):
            return
        self.actions.append(Action(
            5, f"MKDIR {self._relative(path)}/",
            lambda path=path: path.mkdir(parents=True, exist_ok=False),
        ))

    def move(self, src, dst):
        if src.is_symlink():
            self.conflict(f"源是符号链接: {self._relative(src)}")
            return
        if not self._safe_parents(dst):
            return
        if dst.is_symlink() or dst.exists():
            self.conflict(
                f"归档/迁移目标已存在，原件保留不解链: {self._relative(dst)}"
            )
            return
        if not self.reserve(dst, "move"):
            return
        self._removed.add(str(src))

        def perform(src=src, dst=dst):
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))

        self.actions.append(Action(
            10,
            f"MOVE {self._relative(src)} -> {self._relative(dst)}",
            perform,
        ))

    def write(self, path, content, *, strict=False, label="WRITE"):
        data = content.encode("utf-8") if isinstance(content, str) else content
        if not self._safe_parents(path):
            return
        if str(path) not in self._removed and (path.is_symlink() or path.exists()):
            if (not strict and not path.is_symlink() and path.is_file()
                    and path.read_bytes() == data):
                self.keep(self._relative(path))
                return
            self.conflict(f"写入目标已存在且不可覆盖: {self._relative(path)}")
            return
        if not self.reserve(path, "write"):
            return

        def perform(path=path, data=data):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        self.actions.append(Action(30, f"{label} {self._relative(path)}", perform))

    def rmdir(self, path):
        self._removed.add(str(path))
        self.actions.append(Action(
            20, f"RMDIR {self._relative(path)}/",
            lambda path=path: path.rmdir() if path.exists() else None,
        ))

    def link(self, path, target):
        if not self._safe_parents(path):
            return
        if path.is_symlink():
            if os.readlink(path) == target:
                self.keep(f"{self._relative(path)} -> {target}")
            else:
                self.conflict(
                    f"符号链接指向冲突: {self._relative(path)} -> {os.readlink(path)}"
                )
            return
        if path.exists() and str(path) not in self._removed:
            self.conflict(f"链接目标已存在且不是符号链接: {self._relative(path)}")
            return
        if not self.reserve(path, "link"):
            return

        def perform(path=path, target=target):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(target)

        self.actions.append(Action(
            40, f"LINK {self._relative(path)} -> {target}", perform
        ))


def _under(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _equivalent_agents_link(path, root):
    if not path.is_symlink():
        return False
    try:
        return (path.parent / os.readlink(path)).resolve() == (root / "AGENTS.md")
    except (OSError, RuntimeError):
        return False


def _safe_without_follow(root, path, *, allow_leaf_link=False):
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    current = root
    for index, part in enumerate(rel.parts):
        if part == ".git":
            return False
        current = current / part
        leaf = index == len(rel.parts) - 1
        if current.is_symlink():
            return leaf and allow_leaf_link
        if not leaf and current.exists() and not current.is_dir():
            return False
    return True


def _routing_table():
    """Extract the fixed harness route from the installation template."""
    lines = (HARNESS / "templates/AGENTS.md").read_text(encoding="utf-8").splitlines()
    heading = next((i for i, line in enumerate(lines)
                    if re.fullmatch(r"#{1,6}\s+路由表\s*", line)), None)
    if heading is None:
        raise ValueError("templates/AGENTS.md 缺少路由表")
    table = []
    for line in lines[heading + 1:]:
        if not line.strip() and not table:
            continue
        if not line.startswith("|"):
            if table:
                break
            continue
        if "[示例：" not in line and "[占位：" not in line:
            table.append(line)
    if (len(table) < 3 or "docs/rules/harness.md" not in "\n".join(table)
            or any(token in "\n".join(table) for token in ("[示例：", "[占位："))):
        raise ValueError("templates/AGENTS.md 的固定路由行不完整")
    return lines[heading] + "\n\n" + "\n".join(table) + "\n"


def _walk(root):
    """Return physical directories and files without following symlinks."""
    directories, files, links, forbidden = [], [], [], []
    for current, names, filenames in os.walk(root, topdown=True, followlinks=False):
        current = Path(current)
        kept_names = []
        for name in sorted(names):
            path = current / name
            if name == ".git":
                # Inspect the directory entry only.  Migration metadata must
                # never turn into a route for reading repository internals.
                forbidden.append(path)
            elif path.is_symlink():
                links.append(path)
            else:
                directories.append(path)
                kept_names.append(name)
        names[:] = kept_names
        for name in sorted(filenames):
            path = current / name
            if path.is_symlink():
                links.append(path)
            else:
                files.append(path)
    return directories, files, links, forbidden


def _task_roots(trellis, plan):
    tasks = trellis / "tasks"
    if not tasks.is_symlink() and not tasks.exists():
        return []
    if tasks.is_symlink() or not tasks.is_dir():
        plan.conflict(".trellis/tasks 类型不安全")
        return []
    found = []
    for child in sorted(tasks.iterdir(), key=lambda p: p.name):
        if child.name == "archive":
            continue
        if child.is_symlink():
            plan.conflict(f"源是符号链接: {plan._relative(child)}")
        elif child.is_dir():
            metadata = child / "task.json"
            if not metadata.is_symlink() and metadata.is_file():
                found.append(child)
    archive = tasks / "archive"
    if archive.is_symlink() or archive.exists():
        if archive.is_symlink() or not archive.is_dir():
            plan.conflict(".trellis/tasks/archive 类型不安全")
        else:
            directories, files, links, forbidden = _walk(archive)
            for link in links:
                plan.conflict(f"源是符号链接: {plan._relative(link)}")
            for path in forbidden:
                plan.conflict(f"拒绝读取内嵌 .git: {plan._relative(path)}")
            for task_json in files:
                if task_json.name == "task.json":
                    found.append(task_json.parent)
    unique = []
    seen = set()
    for item in sorted(found, key=lambda p: p.relative_to(trellis).as_posix()):
        if str(item) not in seen:
            seen.add(str(item))
            unique.append(item)
    return unique


def _read_task(path, plan):
    metadata = path / "task.json"
    if metadata.is_symlink() or not metadata.is_file():
        plan.conflict(f"任务元数据类型不对: {plan._relative(metadata)}")
        return None
    try:
        value = json.loads(metadata.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        plan.conflict(f"任务元数据无法解析: {plan._relative(metadata)} ({exc})")
        return None
    if not isinstance(value, dict):
        plan.conflict(f"任务元数据必须是 JSON object: {plan._relative(metadata)}")
        return None
    status = value.get("status")
    if not isinstance(status, str):
        plan.conflict(
            f"Trellis 状态必须是字符串 {status!r}: {plan._relative(metadata)}"
        )
        return None
    if status not in STATUS_DEST:
        plan.conflict(f"未知 Trellis 状态 {status!r}: {plan._relative(metadata)}")
        return None
    title = value.get("title")
    if not isinstance(title, str) or not title.strip():
        title = path.name
    return status, title.strip()


def _role(rel):
    posix = rel.as_posix()
    name = rel.name
    if posix == "prd.md":
        return "需求与验收"
    if name.startswith("design") and name.endswith(".md"):
        return "设计"
    if name.startswith("implement") and name.endswith(".md"):
        return "实施步骤"
    if rel.parts and rel.parts[0] == "research":
        return "调研"
    if rel.parts and rel.parts[0] == "dispatch":
        return "派工包"
    if name.startswith("协作单") and name.endswith(".md"):
        return "协作单"
    if name.endswith(".jsonl"):
        return "Trellis 上下文清单,已失效仅存档"
    return "原样保留"


def _spec(task_root, source_rel, status, title, scope, migration_date, clock, files):
    if task_root.name == "00-bootstrap-guidelines":
        harness_status = "done"
    else:
        harness_status = STATUS_DEST[status][0]
    lines = [f"Status: {harness_status}"]
    if scope is not None:
        lines.append(f"Scope: {scope}")
    lines.extend([
        f"# {title}",
        "",
        f"来源: Trellis 任务 {source_rel.as_posix()},原状态 {status},迁移于 {migration_date}",
        "",
        "## 文档",
        "",
    ])
    for rel in sorted(files, key=lambda p: p.as_posix()):
        shown = Path("trellis-task.json") if rel == Path("task.json") else rel
        lines.append(f"- {shown.as_posix()} — {_role(shown)}")
    lines.extend(["", "## 进展", ""])
    stamp = f"{migration_date[5:]} {clock}"
    if task_root.name == "00-bootstrap-guidelines":
        lines.append(
            f"- {stamp} done: Trellis 拆除,规范改由 docs/rules/ 承接"
            " | next: 无 | 别再试: 无"
        )
    else:
        lines.append(
            f"- {stamp} done: 从 Trellis 迁入(原状态 {status})"
            " | next: 按 prd.md 继续 | 别再试: 无"
        )
    return "\n".join(lines) + "\n"


def _normalize_scope(root, raw, plan):
    candidate = Path(raw)
    if (not raw or candidate == Path(".") or candidate.is_absolute()
            or any(p in ("", ".", "..") for p in candidate.parts)
            or ".git" in candidate.parts):
        plan.conflict(f"非法 Scope: {raw!r}")
        return None
    current = root
    for part in candidate.parts:
        current = current / part
        if current.is_symlink():
            plan.conflict(f"Scope 经过符号链接: {raw}")
            return None
        if current.exists() and not current.is_dir():
            plan.conflict(f"Scope 不是目录: {raw}")
            return None
    try:
        current.resolve().relative_to(root)
    except ValueError:
        plan.conflict(f"Scope 越出项目: {raw}")
        return None
    normalized = candidate.as_posix().rstrip("/") + "/"
    return normalized


def _plan_tasks(plan, trellis, scopes, migration_date, clock):
    roots = _task_roots(trellis, plan)
    used_scopes = set()
    task_roots = set(roots)
    for task_root in roots:
        parsed = _read_task(task_root, plan)
        if parsed is None:
            continue
        status, title = parsed
        directories, files, links, forbidden = _walk(task_root)
        for link in links:
            plan.conflict(f"任务内含符号链接: {plan._relative(link)}")
        for path in forbidden:
            plan.conflict(f"拒绝读取内嵌 .git: {plan._relative(path)}")
        root_rels = [path.relative_to(task_root) for path in files]
        if Path("spec.md") in root_rels:
            plan.conflict(f"原任务 spec.md 与迁移生成文件冲突: {plan._relative(task_root / 'spec.md')}")
        if Path("trellis-task.json") in root_rels:
            plan.conflict(f"原任务 trellis-task.json 与重命名目标冲突: {plan._relative(task_root / 'trellis-task.json')}")
        if task_root.name == "00-bootstrap-guidelines":
            destination = plan.root / ".scratch/archive" / task_root.name
        else:
            destination = plan.root / STATUS_DEST[status][1] / task_root.name
        plan.mkdir(destination, strict=True)
        scope = scopes.get(task_root.name)
        if scope is not None:
            used_scopes.add(task_root.name)
        source_rel = task_root.relative_to(plan.root)
        plan.write(
            destination / "spec.md",
            _spec(task_root, source_rel, status, title, scope,
                  migration_date, clock, root_rels),
            strict=True,
        )
        for directory in directories:
            rel = directory.relative_to(task_root)
            plan.mkdir(destination / rel)
        for src in files:
            rel = src.relative_to(task_root)
            if rel == Path("spec.md") or rel == Path("trellis-task.json"):
                continue
            dst_rel = Path("trellis-task.json") if rel == Path("task.json") else rel
            plan.move(src, destination / dst_rel)
    for name in sorted(set(scopes) - used_scopes):
        plan.conflict(f"--scope 指定了不存在的任务: {name}")
    return task_roots


def _plan_trellis_remainder(plan, trellis, task_roots):
    directories, files, links, forbidden = _walk(trellis)
    for link in links:
        plan.conflict(f".trellis 内含符号链接: {plan._relative(link)}")
    for path in forbidden:
        plan.conflict(f"拒绝读取内嵌 .git: {plan._relative(path)}")
    archive_root = plan.root / ARCHIVE / ".trellis"
    plan.mkdir(archive_root)
    for directory in directories:
        if any(_under(directory, task) for task in task_roots):
            continue
        plan.mkdir(archive_root / directory.relative_to(trellis))
    for src in files:
        if any(_under(src, task) for task in task_roots):
            continue
        plan.move(src, archive_root / src.relative_to(trellis))
    for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True):
        plan.rmdir(directory)
    plan.rmdir(trellis)


def _contains_trellis(name):
    return "trellis" in name.lower()


def _validate_moved_tree(path, plan):
    if path.is_symlink():
        plan.conflict(f"平台迁移源是符号链接: {plan._relative(path)}")
        return False
    if path.is_dir():
        _, _, links, forbidden = _walk(path)
        for link in links:
            plan.conflict(f"平台迁移树内含符号链接: {plan._relative(link)}")
        for item in forbidden:
            plan.conflict(f"拒绝读取内嵌 .git: {plan._relative(item)}")
        return not links and not forbidden
    return path.is_file()


def _matched_platform_items(base, exact_names):
    selected, forbidden = [], []
    for current, names, files in os.walk(base, topdown=True, followlinks=False):
        current = Path(current)
        kept = []
        for name in sorted(names):
            path = current / name
            if name == ".git":
                forbidden.append(path)
            elif _contains_trellis(name) or name in exact_names:
                selected.append(path)
            else:
                kept.append(name)
        names[:] = kept
        for name in sorted(files):
            if name == ".git":
                forbidden.append(current / name)
            elif _contains_trellis(name) or name in exact_names:
                selected.append(current / name)
    return selected, forbidden


def _plan_platform(plan):
    for rel_text in PLATFORM_DIRS:
        base = plan.root / rel_text
        if not plan._safe_parents(base):
            continue
        if not base.is_symlink() and not base.exists():
            continue
        if base.is_symlink():
            if rel_text == ".codex/hooks" and os.readlink(base) == "../.claude/hooks":
                continue
            plan.conflict(f"平台目录是符号链接: {rel_text}")
            continue
        if not base.is_dir():
            plan.conflict(f"平台路径不是目录: {rel_text}")
            continue
        exact = LEGACY_SCRIPTS if rel_text in (".claude/hooks", ".codex/hooks") else set()
        if rel_text == ".codex/hooks":
            children = sorted(base.iterdir(), key=lambda p: p.name)
            for child in children:
                if not (_contains_trellis(child.name) or child.name in exact):
                    plan.conflict(
                        f".codex/hooks 含未识别项，无法安全换成链接: {child.name}"
                    )
            selected = [p for p in children
                        if _contains_trellis(p.name) or p.name in exact]
        else:
            selected, forbidden = _matched_platform_items(base, exact)
            for path in forbidden:
                plan.conflict(f"拒绝读取内嵌 .git: {plan._relative(path)}")
        for src in selected:
            if _validate_moved_tree(src, plan):
                plan.move(src, plan.root / ARCHIVE / "platform" / src.relative_to(plan.root))
        if rel_text == ".codex/hooks":
            plan.rmdir(base)


def _clean_hooks_json(raw, path, plan):
    try:
        data = json.loads(raw) if raw is not None else {}
    except ValueError as exc:
        plan.conflict(f"{path} 不是合法 JSON ({exc})")
        return None
    if not isinstance(data, dict):
        plan.conflict(f"{path} 必须是 JSON object")
        return None
    hooks = data.get("hooks")
    if hooks is not None and not isinstance(hooks, dict):
        plan.conflict(f"{path} hooks 必须是 object")
        return None
    if isinstance(hooks, dict):
        for event in list(hooks):
            groups = hooks[event]
            if not isinstance(groups, list):
                plan.conflict(f"{path} hooks.{event} 必须是 array")
                continue
            cleaned_groups = []
            for group in groups:
                if not isinstance(group, dict) or not isinstance(group.get("hooks", []), list):
                    plan.conflict(f"{path} hooks.{event} 含非法 group")
                    continue
                handlers = []
                for handler in group.get("hooks", []):
                    if not isinstance(handler, dict):
                        plan.conflict(f"{path} hooks.{event} 含非法 handler")
                        continue
                    command = handler.get("command")
                    if isinstance(command, str) and any(name in command for name in LEGACY_SCRIPTS):
                        continue
                    handlers.append(handler)
                if handlers:
                    copied = dict(group)
                    copied["hooks"] = handlers
                    cleaned_groups.append(copied)
            if cleaned_groups:
                hooks[event] = cleaned_groups
            else:
                del hooks[event]
    if plan.conflicts:
        return None
    return data


def _merged_json(data, prefix):
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "hooks.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        init.merge_hooks(path, prefix)
        return path.read_text(encoding="utf-8")


def _replace_with_archive(plan, path, content):
    data = content.encode("utf-8") if isinstance(content, str) else content
    if path.is_symlink() or (path.exists() and not path.is_file()):
        plan.conflict(f"配置路径类型冲突: {plan._relative(path)}")
        return
    if path.is_file() and path.read_bytes() == data:
        plan.keep(plan._relative(path))
        return
    if path.is_file():
        plan.move(path, plan.root / ARCHIVE / "platform" / path.relative_to(plan.root))
    plan.write(path, data)


def _plan_configs(plan):
    final_codex = None
    for rel, prefix in (
        (Path(".claude/settings.json"), '"$CLAUDE_PROJECT_DIR"/.claude/hooks'),
        (Path(".codex/hooks.json"), ".codex/hooks"),
    ):
        path = plan.root / rel
        if not plan._safe_parents(path):
            continue
        if path.is_symlink() or (path.exists() and not path.is_file()):
            plan.conflict(f"配置路径类型冲突: {rel.as_posix()}")
            continue
        try:
            raw = path.read_text(encoding="utf-8") if path.is_file() else None
        except (OSError, UnicodeError) as exc:
            plan.conflict(f"无法读取 {rel.as_posix()}: {exc}")
            continue
        data = _clean_hooks_json(raw, rel.as_posix(), plan)
        if data is not None:
            try:
                desired = _merged_json(data, prefix)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                plan.conflict(f"无法合并 {rel.as_posix()}: {exc}")
                continue
            if rel == Path(".codex/hooks.json"):
                final_codex = desired
            _replace_with_archive(plan, path, desired)

    toml = plan.root / ".codex/config.toml"
    if not plan._safe_parents(toml):
        pass
    elif toml.is_symlink() or (toml.exists() and not toml.is_file()):
        plan.conflict("配置路径类型冲突: .codex/config.toml")
    elif toml.is_file():
        try:
            lines = toml.read_text(encoding="utf-8").splitlines(keepends=True)
        except (OSError, UnicodeError) as exc:
            plan.conflict(f"无法读取 .codex/config.toml: {exc}")
        else:
            desired = "".join(
                line for line in lines
                if not (line.lstrip().startswith("#") and re.search("trellis", line, re.I))
            )
            _replace_with_archive(plan, toml, desired)
    return final_codex


def _transform_agents(text, plan, routing_table):
    start = "<!-- TRELLIS:START -->"
    end = "<!-- TRELLIS:END -->"
    starts = [m.start() for m in re.finditer(re.escape(start), text)]
    ends = [m.start() for m in re.finditer(re.escape(end), text)]
    if starts or ends:
        if len(starts) != 1 or len(ends) != 1 or starts[0] > ends[0]:
            plan.conflict("AGENTS.md 的 TRELLIS 管理块标记不完整")
            return None
        after_end = ends[0] + len(end)
        before = text[:starts[0]].rstrip()
        after = text[after_end:].lstrip()
        if before and after:
            text = before + "\n\n" + after
        elif before:
            text = before + "\n"
        elif after:
            text = after
        else:
            text = ""
    if not re.search(r"^#{1,6}\s+路由表\s*$", text, re.M):
        text = text.rstrip() + ("\n\n" if text.strip() else "") + routing_table
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def _plan_text_files(plan):
    try:
        routing_table = _routing_table()
    except (OSError, UnicodeError, ValueError) as exc:
        plan.conflict(f"无法从 templates/AGENTS.md 读取固定路由表: {exc}")
        return
    agents = plan.root / "AGENTS.md"
    if agents.is_symlink() or (agents.exists() and not agents.is_file()):
        plan.conflict("AGENTS.md 类型不对")
    elif agents.is_file():
        try:
            original = agents.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            plan.conflict(f"无法读取 AGENTS.md: {exc}")
        else:
            desired = _transform_agents(original, plan, routing_table)
            if desired is not None and desired != original:
                # This is a content edit, not a source-file removal.
                plan._removed.add(str(agents))
                plan.actions.append(Action(
                    30, "WRITE AGENTS.md",
                    lambda agents=agents, desired=desired: agents.write_text(desired, encoding="utf-8"),
                ))
            elif desired is not None:
                plan.keep("AGENTS.md")
            if desired is not None:
                for number, line in enumerate(desired.splitlines(), 1):
                    if re.search(r"trellis|\.trellis/", line, re.I):
                        plan.notes.append(f"AGENTS.md:{number}: {line}")
    else:
        plan.write(agents, routing_table)

    attributes = plan.root / ".gitattributes"
    if attributes.is_symlink() or (attributes.exists() and not attributes.is_file()):
        plan.conflict(".gitattributes 类型不对")
    elif attributes.is_file():
        try:
            original = attributes.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            plan.conflict(f"无法读取 .gitattributes: {exc}")
        else:
            desired = "".join(
                line for line in original.splitlines(keepends=True) if ".trellis/" not in line
            )
            if desired != original:
                plan._removed.add(str(attributes))
                plan.actions.append(Action(
                    30, "WRITE .gitattributes",
                    lambda attributes=attributes, desired=desired: attributes.write_text(desired, encoding="utf-8"),
                ))
            else:
                plan.keep(".gitattributes")

    ignore = plan.root / ".gitignore"
    if ignore.is_symlink() or (ignore.exists() and not ignore.is_file()):
        plan.conflict(".gitignore 类型不对")
    else:
        try:
            original = ignore.read_text(encoding="utf-8") if ignore.is_file() else ""
        except (OSError, UnicodeError) as exc:
            plan.conflict(f"无法读取 .gitignore: {exc}")
        else:
            if init.GITIGNORE_LINE in original.splitlines():
                plan.keep(".gitignore")
            else:
                separator = "" if not original or original.endswith("\n") else "\n"
                desired = original + separator + init.GITIGNORE_LINE + "\n"
                if ignore.exists():
                    plan._removed.add(str(ignore))
                    plan.actions.append(Action(
                        30, f"WRITE .gitignore (+{init.GITIGNORE_LINE})",
                        lambda ignore=ignore, desired=desired: ignore.write_text(desired, encoding="utf-8"),
                    ))
                else:
                    plan.write(ignore, desired)


def _plan_install(plan):
    expected_files = (
        (HARNESS / "docs/rules/harness.md", Path("docs/rules/harness.md")),
        (HARNESS / ".claude/hooks/session_start.py", Path(".claude/hooks/session_start.py")),
        (HARNESS / ".claude/hooks/stop_guard.py", Path(".claude/hooks/stop_guard.py")),
    )
    base = init.Plan(plan.root)
    for src, rel in expected_files:
        if plan._safe_parents(plan.root / rel):
            base.copy(src, rel.as_posix())
    decisions = plan.root / "docs/decisions.md"
    scratch_keep = plan.root / ".scratch/.gitkeep"
    for path in (decisions, scratch_keep):
        if not plan._safe_parents(path):
            continue
        if path.is_symlink() or (path.exists() and not path.is_file()):
            plan.conflict(f"安装目标类型冲突: {plan._relative(path)}")
        else:
            rel = path.relative_to(plan.root).as_posix()
            base.write_if_missing(rel, init.LEDGER if path == decisions else "")
    skill = plan.root / ".agents/skills/interview-me"
    if plan._safe_parents(skill):
        base.copytree(HARNESS / ".agents/skills/interview-me", ".agents/skills/interview-me")
    for conflict in base.conflicts:
        plan.conflict(conflict)
    for kept in base.kept:
        plan.keep(kept)
    for label, function in base.actions:
        plan.actions.append(Action(30, f"INSTALL {label}", function))

    claude = plan.root / "CLAUDE.md"
    if not plan._safe_parents(claude):
        pass
    elif claude.is_symlink():
        if _equivalent_agents_link(claude, plan.root):
            plan.keep(f"CLAUDE.md -> {os.readlink(claude)}")
        else:
            plan.conflict("CLAUDE.md 符号链接未指向 AGENTS.md")
    elif claude.exists():
        plan.conflict("CLAUDE.md 已存在且不是符号链接")
    else:
        plan.link(claude, "AGENTS.md")
    codex_hooks = plan.root / ".codex/hooks"
    if plan._safe_parents(codex_hooks):
        plan.link(codex_hooks, "../.claude/hooks")
    claude_skill = plan.root / ".claude/skills/interview-me"
    if plan._safe_parents(claude_skill):
        plan.link(claude_skill, "../../.agents/skills/interview-me")


def _fully_migrated(root):
    evidence = root / ARCHIVE / ".trellis"
    if (not _safe_without_follow(root, evidence) or evidence.is_symlink()
            or not evidence.is_dir()):
        return False, [f"缺少迁移归档证据 {ARCHIVE.as_posix()}/.trellis/"]
    problems = []
    for source, rel in (
        (HARNESS / "docs/rules/harness.md", Path("docs/rules/harness.md")),
        (HARNESS / ".claude/hooks/session_start.py", Path(".claude/hooks/session_start.py")),
        (HARNESS / ".claude/hooks/stop_guard.py", Path(".claude/hooks/stop_guard.py")),
    ):
        target = root / rel
        if (not _safe_without_follow(root, target) or target.is_symlink() or not target.is_file()
                or target.read_bytes() != source.read_bytes()):
            problems.append(rel.as_posix())
    skill = root / ".agents/skills/interview-me"
    skill_links = []
    if _safe_without_follow(root, skill) and skill.is_dir() and not skill.is_symlink():
        _, _, skill_links, skill_git = _walk(skill)
    else:
        skill_git = []
    if (not _safe_without_follow(root, skill) or skill.is_symlink() or not skill.is_dir()
            or skill_links or skill_git or not init.same_tree(
                HARNESS / ".agents/skills/interview-me", skill)):
        problems.append(".agents/skills/interview-me/")
    links = (
        (Path("CLAUDE.md"), "AGENTS.md"),
        (Path(".codex/hooks"), "../.claude/hooks"),
        (Path(".claude/skills/interview-me"), "../../.agents/skills/interview-me"),
    )
    for rel, target in links:
        path = root / rel
        if rel == Path("CLAUDE.md"):
            valid = (_safe_without_follow(root, path, allow_leaf_link=True)
                     and _equivalent_agents_link(path, root))
        else:
            valid = (_safe_without_follow(root, path, allow_leaf_link=True)
                     and path.is_symlink() and os.readlink(path) == target)
        if not valid:
            problems.append(f"{rel.as_posix()} -> {target}")
    for rel, prefix in (
        (Path(".claude/settings.json"), '"$CLAUDE_PROJECT_DIR"/.claude/hooks'),
        (Path(".codex/hooks.json"), ".codex/hooks"),
    ):
        path = root / rel
        try:
            if (not _safe_without_follow(root, path) or path.is_symlink()
                    or not path.is_file() or init.missing_hooks(path, prefix)):
                problems.append(rel.as_posix())
        except (OSError, ValueError, TypeError, KeyError):
            problems.append(rel.as_posix())
    agents = root / "AGENTS.md"
    if (not _safe_without_follow(root, agents) or not agents.is_file()
            or agents.is_symlink()):
        problems.append("AGENTS.md")
    else:
        try:
            if not re.search(r"^#{1,6}\s+路由表\s*$", agents.read_text(encoding="utf-8"), re.M):
                problems.append("AGENTS.md 路由表")
        except (OSError, UnicodeError):
            problems.append("AGENTS.md")
    for rel in (Path("docs/decisions.md"), Path(".scratch/.gitkeep")):
        path = root / rel
        if (not _safe_without_follow(root, path) or path.is_symlink()
                or not path.is_file()):
            problems.append(rel.as_posix())
    ignore = root / ".gitignore"
    try:
        if (not _safe_without_follow(root, ignore) or ignore.is_symlink()
                or not ignore.is_file()
                or init.GITIGNORE_LINE not in ignore.read_text(encoding="utf-8").splitlines()):
            problems.append(".gitignore")
    except (OSError, UnicodeError):
        problems.append(".gitignore")
    return not problems, problems


def _trust_entries(root, final_codex_json):
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "hooks.json"
        path.write_text(final_codex_json, encoding="utf-8")
        entries = init.codex_trust_entries(path)
    prefix = str(root / ".codex/hooks.json")
    return [(prefix + key[key.find(":"):], digest) for key, digest in entries]


def build_plan(root, scopes, migration_date, clock):
    plan = MigrationPlan(root)
    trellis = root / ".trellis"
    if trellis.is_symlink():
        plan.conflict(".trellis 是符号链接")
        return plan, None
    if not trellis.exists():
        complete, problems = _fully_migrated(root)
        if complete:
            plan.keep("已完整迁移，.trellis 已归档")
        else:
            plan.conflict(".trellis 不存在，且不是可识别的完整迁移项目")
            for problem in problems:
                plan.conflict(f"完整性缺失: {problem}")
        return plan, None
    if not trellis.is_dir():
        plan.conflict(".trellis 不是目录")
        return plan, None

    normalized_scopes = {}
    for task, raw in scopes.items():
        normalized = _normalize_scope(root, raw, plan)
        if normalized is not None:
            normalized_scopes[task] = normalized
    task_roots = _plan_tasks(plan, trellis, normalized_scopes, migration_date, clock)
    _plan_trellis_remainder(plan, trellis, task_roots)
    _plan_platform(plan)
    final_codex = _plan_configs(plan)
    _plan_text_files(plan)
    _plan_install(plan)
    return plan, final_codex


def _parse(argv):
    parser = Parser(description=__doc__)
    parser.add_argument("root")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--scope", action="append", nargs="+", default=[], metavar="TASK=DIR")
    parser.add_argument("--date", dest="migration_date")
    ns = parser.parse_args(argv)
    scopes = {}
    for group in ns.scope:
        for item in group:
            if "=" not in item:
                raise CliError(f"--scope 必须是 TASK=DIR: {item!r}")
            task, directory = item.split("=", 1)
            if not task or not directory:
                raise CliError(f"--scope 必须是 TASK=DIR: {item!r}")
            if task in scopes:
                raise CliError(f"--scope 任务重复: {task}")
            scopes[task] = directory
    if ns.migration_date:
        try:
            selected = date.fromisoformat(ns.migration_date)
        except ValueError:
            raise CliError(f"--date 必须是 YYYY-MM-DD: {ns.migration_date!r}")
    else:
        selected = date.today()
    raw_root = Path(ns.root).expanduser().absolute()
    if raw_root.is_symlink() or not raw_root.is_dir():
        raise CliError(f"目标必须是非符号链接目录: {raw_root}")
    root = raw_root.resolve()
    return root, ns.apply, scopes, selected.isoformat(), datetime.now().strftime("%H:%M")


def main(argv=None):
    try:
        root, apply, scopes, migration_date, clock = _parse(
            sys.argv[1:] if argv is None else argv
        )
    except CliError as exc:
        print(f"拒绝,未写入任何文件: {exc}")
        return 1

    plan, final_codex = build_plan(root, scopes, migration_date, clock)
    if plan.conflicts:
        print(f"拒绝,未写入任何文件。{root} 有 {len(plan.conflicts)} 处冲突:")
        for conflict in plan.conflicts:
            print(f"  CONFLICT {conflict}")
        return 1

    mode = "APPLY" if apply else "DRY-RUN"
    print(f"{mode} {root}:")
    ordered = sorted(enumerate(plan.actions), key=lambda item: (item[1].phase, item[0]))
    if not ordered:
        print("  NO-OP 已完整迁移，无可执行动作")
    else:
        for _, action in ordered:
            print(f"  {action.label}")
    for kept in plan.kept:
        print(f"  KEEP {kept}")
    for note in plan.notes:
        print(f"  HUMAN {note}")
    if apply:
        try:
            for _, action in ordered:
                action.run()
        except Exception as exc:
            print(f"执行失败: {exc}")
            return 1

    if final_codex is not None:
        print("Codex hook trust entries (只打印,不写用户配置):")
        try:
            for key, digest in _trust_entries(root, final_codex):
                print(f'[hooks.state."{key}"]\ntrusted_hash = "{digest}"')
        except (OSError, ValueError, TypeError, KeyError) as exc:
            print(f"  无法计算 trust entries: {exc}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
