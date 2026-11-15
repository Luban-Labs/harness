#!/usr/bin/env python3
"""Query and validate docs/rules/core-judgments.md on demand; fail open when used from Stop."""

import os
from pathlib import Path
import re
import sys
import time

sys.dont_write_bytecode = True


TIME_BUDGET = 1.5
SECTION_LIMIT = 3
MAX_SECTION_CHARS = 300
MAX_ITEM_CHARS = 120
REQUIRED_FIELDS = ("定义", "唯一实现", "语义例外", "待收口")
ALL_FIELDS = REQUIRED_FIELDS + ("详情",)
MULTI_FIELDS = {"语义例外", "待收口"}
DETAIL_DIR = "docs/judgments"
FIELD_RE = re.compile(r"^-\s*([^:：\s][^:：]*?)\s*[:：]\s*(.*)$")
SUBITEM_RE = re.compile(r"^\s+-\s+(.*)$")
IMPL_LINE_RE = re.compile(r"^`[^`\r\n]+`(?:[\s,，、;；/|]+`[^`\r\n]+`)*$")
SOURCE_TAG_RE = re.compile(r"出处\s*[:：]")
BACKTICK_PATH_RE = re.compile(r"`[^`\r\n]*(?:/|\.[A-Za-z])[^`\r\n]*`")
PROSE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_./-])"
    r"(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+"
    r"|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]*\.[A-Za-z][A-Za-z0-9]{0,7}"
    r"|[A-Za-z0-9_.-]*_[A-Za-z0-9_.-]*\.[A-Za-z][A-Za-z0-9]{0,7})"
    r"(?![A-Za-z0-9_./-])"
)
# Match MM-DD (or YYYY-MM-DD) when not bordered by digits, version dots, or multi-hyphen chains.
DATE_RE = re.compile(
    r"(?<!\d)(?<!\d\.)(?<!\d-)(?:(?:19|20)\d{2}-)?(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])(?!\d)(?!\.\d)(?!-\d)"
)
BACKTICK_RE = re.compile(r"`[^`\r\n]*`")

USAGE = """用法: python3 .claude/hooks/judgments.py <子命令> [参数] [--cwd <目录>]

子命令:
  ls                      列出全部概念名与一句话定义
  show <名> [--detail]    查看单节原文;加 --detail 同时附 docs/judgments/<名>.md
  check                   检查全表形状与孤儿/断链详情文件,有违规退出码为 1
  --help, -h              显示本帮助

形状规则:
  - 每节 <= 300 字;禁「出处:」「出处：」与 MM-DD 日期(前后非数字即算,紧邻字母同禁;文件路径与版本号除外)
  - 必填:定义(一句 <= 120 字)、唯一实现(反引号「路径:名」加分隔符或「待定」)、
    语义例外(每项一行 <= 120 字,无则写「无」)、待收口(同上)
  - 可选:详情(指向 docs/judgments/<概念名>.md;路径及上级不许为符号链接,未链文件算孤儿)"""


def check_time(deadline):
    if deadline is not None and time.monotonic() >= deadline:
        raise TimeoutError("judgment table check ran out of time")


def resolve_root(cwd):
    """Find the active project/worktree root holding docs/rules/core-judgments.md."""
    from session_start import CORE_TABLE, project_roots

    cwd = Path(cwd).resolve()
    scan_root, _ = project_roots(cwd)
    if scan_root is not None and not (scan_root / ".scratch").is_symlink() and (
        (scan_root / CORE_TABLE).exists() or not any((p / CORE_TABLE).exists() for p in (cwd, *cwd.parents))
    ):
        return scan_root
    for parent in (cwd, *cwd.parents):
        if (parent / CORE_TABLE).exists():
            return parent
    return scan_root or cwd


def parse_section_fields(section):
    """Parse top-level fields and indented list items from a section; return (seen, items, errors)."""
    seen, items, errors, current_field, bad_line_noted = {}, {}, [], None, False
    for line in section.splitlines()[1:]:
        if not line.strip():
            continue
        match = FIELD_RE.match(line)
        if match:
            field, value = match.group(1).strip(), match.group(2).strip()
            current_field = field
            if field not in ALL_FIELDS:
                errors.append(f"未知字段「{field}」")
                continue
            if field in seen:
                errors.append(f"字段「{field}」重复")
                continue
            seen[field] = value
            items[field] = [value] if value else []
            continue
        sub = SUBITEM_RE.match(line)
        if sub and current_field in MULTI_FIELDS:
            item = sub.group(1).strip()
            if not item:
                errors.append(f"「{current_field}」有空子项")
            else:
                items[current_field].append(item)
            continue
        if not bad_line_noted:
            errors.append("含字段以外的行或多行折行")
            bad_line_noted = True
    return seen, items, errors


def check_definition(value):
    """Validate 定义: non-empty, single sentence, <= 120 chars."""
    if not value or value in ("无", "无。"):
        return ["定义不能为空"]
    issues = []
    if len(value) > MAX_ITEM_CHARS:
        issues.append(f"定义 {len(value)} 字,超过 {MAX_ITEM_CHARS} 字")
    stripped = BACKTICK_RE.sub("", value).strip().rstrip("。！？!?. \t")
    if re.search(r"[。！？]", stripped) or re.search(r"(?<=\S)\.\s+[A-Za-z]", stripped):
        issues.append("定义须为一句")
    return issues


def check_implementation(value, root):
    """Validate 唯一实现: backticked project-relative path:name references or 「待定」."""
    from session_start import parse_implementation_ref

    if not value:
        return ["唯一实现不能为空"]
    if value == "待定":
        return []
    if not IMPL_LINE_RE.fullmatch(value):
        return ["唯一实现只许反引号「路径:名」加分隔符或「待定」"]
    for token in re.findall(r"`([^`\r\n]+)`", value):
        try:
            parsed = parse_implementation_ref(token, root)
        except (OSError, RuntimeError, ValueError):
            parsed = None
        if parsed is None:
            return ["唯一实现只许有效的项目相对「路径:名」"]
    return []


def has_forbidden_date(section):
    """Detect forbidden MM-DD/YYYY-MM-DD dates while ignoring file paths and dotted/chained version numbers."""
    scrubbed = BACKTICK_PATH_RE.sub(" ", section)
    scrubbed = PROSE_PATH_RE.sub(lambda m: " " if re.search(r"[A-Za-z]", m.group(0)) else m.group(0), scrubbed)
    return DATE_RE.search(scrubbed) is not None


def inspect_detail_file(root, name):
    """Verify docs/judgments/<name>.md has no symlink component and stays within resolved project root."""
    if not name or name in (".", "..") or ".." in name or any(ch in name for ch in "/\\\x00\r\n"):
        return "bad_name", f"概念名含非法路径字符,不能链接详情: {name}", None
    resolved_root, expected = Path(root).resolve(), f"{DETAIL_DIR}/{name}.md"
    current = resolved_root
    try:
        for part in Path(DETAIL_DIR).parts:
            current = current / part
            if current.is_symlink():
                return "symlink", f"详情路径不许为符号链接: {expected}", None
            if not current.is_dir():
                return "missing", f"详情文件不存在: {expected}", None
        detail_file = current / f"{name}.md"
        if detail_file.is_symlink():
            return "symlink", f"详情路径不许为符号链接: {expected}", None
        if not detail_file.is_file():
            return "missing", f"详情文件不存在: {expected}", None
        detail_dir_real, file_real = current.resolve(), detail_file.resolve()
        if (not detail_dir_real.is_relative_to(resolved_root)
                or not file_real.is_relative_to(resolved_root)
                or file_real.parent != detail_dir_real):
            return "outside", f"详情文件越出项目根: {expected}", None
    except (OSError, RuntimeError, ValueError):
        return "error", f"详情文件不可读: {expected}", None
    return "ok", "", detail_file


def read_no_follow(path):
    """Read a UTF-8 file using O_NOFOLLOW when available so a swapped symlink is never followed."""
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), encoding="utf-8") as stream:
        return stream.read()


def check_detail(name, value, root):
    """Validate 详情 field and return (errors, linked_rel_or_None)."""
    if not value:
        return ["详情不能为空"], None
    if value == "无":
        return [], None
    target = value[1:-1].strip() if len(value) >= 2 and value.startswith("`") and value.endswith("`") else value
    expected = f"{DETAIL_DIR}/{name}.md"
    status, message, _ = inspect_detail_file(root, name)
    if status == "bad_name":
        return [message], None
    if target != expected:
        return [f"详情须指向 {expected}"], None
    return ([], expected) if status == "ok" else ([message], None)


def section_issues(name, section, root, deadline=None):
    """Validate one section against all shape rules; return (problems, linked_detail)."""
    check_time(deadline)
    problems = []
    if len(section) > MAX_SECTION_CHARS:
        problems.append(f"整节 {len(section)} 字,超过 {MAX_SECTION_CHARS} 字")
    if SOURCE_TAG_RE.search(section):
        problems.append("含「出处:」")
    if has_forbidden_date(section):
        problems.append("含 MM-DD 日期")
    seen, items, line_errors = parse_section_fields(section)
    problems.extend(line_errors)
    missing = [field for field in REQUIRED_FIELDS if field not in seen]
    if missing:
        problems.append("缺字段: " + "、".join(missing))
    if "定义" in seen:
        problems.extend(check_definition(seen["定义"]))
    if "唯一实现" in seen:
        problems.extend(check_implementation(seen["唯一实现"], root))
    for field in ("语义例外", "待收口"):
        field_items = items.get(field, []) if field in seen else None
        if field_items is None:
            continue
        if not field_items:
            problems.append(f"「{field}」不能为空,无则写「无」")
        elif (over := [len(item) for item in field_items if len(item) > MAX_ITEM_CHARS]):
            problems.append(f"「{field}」有项 {max(over)} 字,超过 {MAX_ITEM_CHARS} 字")
    linked = None
    if "详情" in seen:
        check_time(deadline)
        detail_errors, linked = check_detail(name, seen["详情"], root)
        problems.extend(detail_errors)
    return problems, linked


def _check_entry_path(path, resolved_root, kind, linked):
    rel = path.relative_to(resolved_root).as_posix()
    if path.is_symlink():
        return (rel, "详情路径不许为符号链接"), False
    try:
        inside = path.resolve().is_relative_to(resolved_root)
    except (OSError, RuntimeError, ValueError):
        return (rel, f"详情{kind}不可读"), False
    if not inside:
        return (rel, f"详情{kind}越出项目根"), False
    if kind == "文件" and rel not in linked:
        return (rel, "孤儿详情文件,没有节的「详情」指向它"), False
    return None, kind == "目录"


def orphan_details(root, linked, deadline=None):
    """List invalid or unreferenced entries under docs/judgments/ within deadline."""
    check_time(deadline)
    resolved_root = current = Path(root).resolve()
    try:
        for part in Path(DETAIL_DIR).parts:
            current = current / part
            if current.is_symlink():
                return [(current.relative_to(resolved_root).as_posix(), "详情路径不许为符号链接")]
        if not current.exists():
            return []
        if not current.is_dir():
            return [(DETAIL_DIR, "详情目录不是普通目录")]
        if not current.resolve().is_relative_to(resolved_root):
            return [(DETAIL_DIR, "详情目录越出项目根")]
    except (OSError, RuntimeError, ValueError):
        return [(DETAIL_DIR, "详情目录不可读")]
    orphans = []
    for folder, dirs, files in os.walk(current, topdown=True, followlinks=False):
        check_time(deadline)
        folder_path, kept = Path(folder), []
        for entry in sorted(dirs):
            check_time(deadline)
            issue, keep = _check_entry_path(folder_path / entry, resolved_root, "目录", linked)
            if issue:
                orphans.append(issue)
            if keep:
                kept.append(entry)
        dirs[:] = kept
        for filename in sorted(files):
            check_time(deadline)
            issue, _ = _check_entry_path(folder_path / filename, resolved_root, "文件", linked)
            if issue:
                orphans.append(issue)
    check_time(deadline)
    return orphans


def table_issues(root, entries=None, deadline=None):
    """Single source of truth for core-judgments.md shape checks used by CLI check and Stop."""
    from session_start import core_judgment_entries

    check_time(deadline)
    root = Path(root).resolve()
    entries = core_judgment_entries(root, deadline) if entries is None else entries
    seen_names, linked, section_errors = set(), set(), []
    for name, _, section in entries:
        check_time(deadline)
        problems, detail_rel = section_issues(name, section, root, deadline=deadline)
        if name in seen_names:
            problems.append("概念名重复")
        seen_names.add(name)
        if detail_rel is not None:
            linked.add(detail_rel)
        if problems:
            section_errors.append((name, problems))
    check_time(deadline)
    orphans = orphan_details(root, linked, deadline=deadline)
    check_time(deadline)
    return section_errors, orphans


def edited_table_worktree(edits, roots, root, deadline):
    """Return (worktree, edited_root, target_rel) if this turn successfully edited core-judgments.md."""
    from session_start import CORE_TABLE
    from stop_evidence import EDIT_TOOLS, locate

    project = Path(root).resolve()
    base = next((path for path in roots if project.is_relative_to(path)), None)
    if base is None:
        return None
    prefix = project.relative_to(base).as_posix()
    target_rel = CORE_TABLE if prefix == "." else f"{prefix}/{CORE_TABLE}"
    for _, tool, data in edits:
        check_time(deadline)
        paths = list(data) if tool == "FileChange" else [data.get(EDIT_TOOLS.get(tool))]
        if tool == "FileChange":
            paths.extend(change.get("move_path") for change in data.values() if isinstance(change, dict))
        for value in paths:
            located = locate(value, roots)
            if located is not None and located[2] == target_rel:
                worktree = located[1]
                edited_root = worktree if prefix == "." else worktree / prefix
                return worktree, edited_root, target_rel
    return None


def reminder(payload, cwd, root):
    """Remind when core-judgments.md sections changed this turn violate the card shape rules."""
    from session_start import CORE_TABLE, core_judgment_entries
    from stop_evidence import git, shown, turn_edits, worktree_roots

    deadline = time.monotonic() + TIME_BUDGET
    check_time(deadline)
    edits = turn_edits(payload, deadline)
    check_time(deadline)
    if not edits:
        return None
    roots = worktree_roots(cwd, deadline)
    check_time(deadline)
    if not roots:
        return None
    hit = edited_table_worktree(edits, roots, root, deadline)
    check_time(deadline)
    if hit is None:
        return None
    worktree, edited_root, target_rel = hit
    table_file = worktree / target_rel
    if table_file.is_symlink() or not table_file.is_file():
        return None
    try:
        disk_text = read_no_follow(table_file)
    except (OSError, UnicodeError):
        return None
    check_time(deadline)
    after_entries = core_judgment_entries(edited_root, deadline, text=disk_text)
    if not after_entries:
        return None
    head_text = git(worktree, deadline, "show", f"HEAD:{target_rel}")
    check_time(deadline)
    before = {}
    for name, _, sec in (core_judgment_entries(edited_root, deadline, text=head_text) if head_text is not None else ()):
        check_time(deadline)
        before.setdefault(name, []).append(sec)
    after = {}
    for name, _, sec in after_entries:
        check_time(deadline)
        after.setdefault(name, []).append(sec)
    section_errors, _ = table_issues(edited_root, entries=after_entries, deadline=deadline)
    merged = {}
    for name, problems in section_errors:
        check_time(deadline)
        if before.get(name) != after.get(name):
            merged.setdefault(name, []).extend(p for p in problems if p not in merged.get(name, ()))
    if not merged:
        return None
    items = list(merged.items())
    listed = "、".join(shown(f"{name}({'/'.join(problems)})") for name, problems in items[:SECTION_LIMIT])
    message = (
        f"[harness] {CORE_TABLE} 本轮改过的节不合形状:{listed}(共 {len(items)} 节)。"
        "照 docs/rules/harness.md「核心判断只写一份」修改并跑 python3 .claude/hooks/judgments.py check。"
    )
    check_time(deadline)
    return message


def load_table(root):
    """Read and parse core-judgments.md for CLI commands; raise ValueError on missing/unreadable file."""
    from session_start import CORE_TABLE, core_judgment_entries

    path = root / CORE_TABLE
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"找不到核心判断表: {CORE_TABLE}")
    try:
        text = read_no_follow(path)
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"无法读取 {CORE_TABLE}: {exc}") from exc
    entries = core_judgment_entries(root, text=text)
    if not entries and re.search(r"^## \S", text, re.M):
        raise ValueError(f"无法解析 {CORE_TABLE}(可能含过长或循环路径)")
    return entries


def cmd_ls(root):
    for name, _, section in load_table(root):
        defn = parse_section_fields(section)[0].get("定义", "")
        print(f"{name}: {defn}" if defn else name)
    return 0


def cmd_show(root, name, with_detail):
    matches = [(n, sec) for n, _, sec in load_table(root) if n == name]
    if not matches:
        print(f"找不到概念: {name}", file=sys.stderr)
        return 1
    body = "\n\n".join(sec for _, sec in matches)
    if not with_detail:
        print(body)
        return 0
    detail_decl = next((parse_section_fields(sec)[0].get("详情", "") for _, sec in matches
                        if parse_section_fields(sec)[0].get("详情", "") not in ("", "无")), "")
    status, message, detail_file = inspect_detail_file(root, name)
    if status in ("symlink", "outside", "error") or (status != "ok" and detail_decl):
        print(message, file=sys.stderr)
        return 1
    content = ""
    if status == "ok":
        try:
            content = read_no_follow(detail_file).rstrip("\n")
        except (OSError, UnicodeError) as exc:
            print(f"详情文件不可读: {DETAIL_DIR}/{name}.md ({exc})", file=sys.stderr)
            return 1
    print(f"{body}\n\n{content}" if content else body)
    return 0


def cmd_check(root):
    from session_start import CORE_TABLE
    from stop_evidence import shown

    section_errors, orphans = table_issues(root, entries=load_table(root))
    for name, problems in section_errors:
        for problem in problems:
            print(f"{CORE_TABLE} [{shown(name)}]: {shown(problem)}")
    for orphan, reason in orphans:
        print(f"{shown(orphan)}: {reason}")
    return 1 if (section_errors or orphans) else 0


def cli(argv):
    args = list(argv)
    if not args or any(flag in args for flag in ("--help", "-h")):
        print(USAGE.rstrip("\n"))
        return 0 if args else 1
    cwd, cleaned, index = Path(os.getcwd()), [], 0
    while index < len(args):
        if args[index] == "--cwd" and index + 1 < len(args):
            cwd, index = Path(args[index + 1]), index + 2
        elif args[index] == "--cwd":
            print("参数错误: --cwd 缺少目录", file=sys.stderr)
            return 1
        else:
            cleaned.append(args[index])
            index += 1
    if not cwd.is_dir():
        print(f"目录不存在: {cwd}", file=sys.stderr)
        return 1
    if not cleaned:
        print(USAGE.rstrip("\n"), file=sys.stderr)
        return 1
    root, cmd, rest = resolve_root(cwd), cleaned[0], cleaned[1:]
    try:
        if cmd == "ls" and not rest:
            return cmd_ls(root)
        if cmd == "check" and not rest:
            return cmd_check(root)
        if cmd == "show":
            with_detail = "--detail" in rest
            names = [item for item in rest if item != "--detail"]
            if len(names) == 1 and not names[0].startswith("-"):
                return cmd_show(root, names[0], with_detail)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"参数错误: {' '.join(args)}\n\n{USAGE.rstrip()}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
