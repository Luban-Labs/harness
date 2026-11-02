#!/usr/bin/env python3
"""Remind when this turn touched a registered name whose whole-file definition changed."""

import ast
from collections import Counter
from pathlib import Path
import re
import time


TIME_BUDGET = 1.5
ARCHITECTURE = "docs/rules/architecture.md"
NAME_BOUNDARY = r"(?<![\w$]){}(?![\w$])"
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def check_time(deadline):
    if time.monotonic() >= deadline:
        raise TimeoutError("dictionary check ran out of time")


def assigned_names(target):
    """Plain names bound by an assignment target; attributes and subscripts bind no name."""
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, (ast.Tuple, ast.List)):
        for element in target.elts:
            yield from assigned_names(element)
    elif isinstance(target, ast.Starred):
        yield from assigned_names(target.value)


def definition_signatures(text, deadline):
    """Count each name's definition signatures in one Python file.

    Functions and classes at any depth keep their enclosing names, decorators, type parameters,
    parameters, return annotation, bases and keywords; module- and class-level assignments count
    only where the name is bound. Bodies and values are excluded, so a body-only or value-only
    change compares equal.
    """
    found = {}
    stack = [(ast.parse(text), (), False)]
    while stack:
        check_time(deadline)
        node, scope, in_function = stack.pop()
        inner = scope
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            header = (scope, type(node).__name__, tuple(ast.dump(item) for item in node.decorator_list),
                      tuple(ast.dump(item) for item in getattr(node, "type_params", ())))
            if isinstance(node, ast.ClassDef):
                signature = header + (tuple(ast.dump(base) for base in node.bases),
                                      tuple(ast.dump(keyword) for keyword in node.keywords))
            else:
                signature = header + (ast.dump(node.args), ast.dump(node.returns) if node.returns else None)
            found.setdefault(node.name, Counter())[signature] += 1
            inner = scope + (node.name,)
        elif not in_function and isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for name in assigned_names(target):
                    found.setdefault(name, Counter())[(scope, "Assign")] += 1
        inside = in_function or isinstance(node, FUNCTIONS)
        stack.extend((child, inner, inside) for child in ast.iter_child_nodes(node))
    return found


def reminder(payload, cwd, root):
    from session_start import CORE_TABLE, core_judgment_entries
    from stop_evidence import EDIT_TOOLS, edit_pieces, git, locate, shown, turn_edits, worktree_roots

    deadline = time.monotonic() + TIME_BUDGET
    entries = core_judgment_entries(root, deadline)
    roots = worktree_roots(cwd, deadline)
    project = Path(root).resolve()
    base = next((path for path in roots if project.is_relative_to(path)), None)
    if base is None:
        return None
    # The table names paths from the project root, which may sit below the git top level.
    prefix = project.relative_to(base).as_posix()

    def scoped(relative):
        return relative if prefix == "." else f"{prefix}/{relative}"

    owners = {}
    by_path = {}
    for concept, implementations in entries:
        for relative, name in implementations:
            if relative.endswith(".py"):
                owners.setdefault((scoped(relative), name), []).append(concept)
                by_path.setdefault(scoped(relative), set()).add(name)
    if not owners:
        return None
    edits = turn_edits(payload, deadline)
    for _, tool, data in edits:
        check_time(deadline)
        paths = list(data) if tool == "FileChange" else [data.get(EDIT_TOOLS.get(tool))]
        if tool == "FileChange":
            paths.extend(change.get("move_path") for change in data.values() if isinstance(change, dict))
        for value in paths:
            located = locate(value, roots)
            if located and located[2] in (scoped(CORE_TABLE), scoped(ARCHITECTURE)):
                return None

    candidates = set()
    for _, tool, data in edits:
        check_time(deadline)
        for value, old, new in edit_pieces(tool, data):
            paths = [value]
            if tool == "FileChange":
                paths.extend([path for path, change in data.items()
                              if isinstance(change, dict) and change.get("move_path") == value])
            for candidate in paths:
                located = locate(candidate, roots)
                if located is None or located[2] not in by_path:
                    continue
                _, worktree, relative = located
                names = by_path[relative]
                # old None replaces HEAD's whole text and a move empties its source: every name counts.
                if old is not None and candidate == value:
                    pieces = [piece for piece in (old, new) if isinstance(piece, str)]
                    names = [name for name in names
                             if any(re.search(NAME_BOUNDARY.format(re.escape(name)), piece) for piece in pieces)]
                candidates.update((worktree, relative, name) for name in names)
    changed = set()
    by_file = {}
    for worktree, relative, name in candidates:
        by_file.setdefault((worktree, relative), set()).add(name)
    for (worktree, relative), names in by_file.items():
        check_time(deadline)
        before = git(worktree, deadline, "show", f"HEAD:{relative}")
        if before is None:
            continue
        try:
            try:
                after = (worktree / relative).read_text(encoding="utf-8-sig")
            except FileNotFoundError:
                after = ""
            old_signatures = definition_signatures(before[1:] if before.startswith("\ufeff") else before, deadline)
            new_signatures = definition_signatures(after, deadline)
        except (OSError, UnicodeError, SyntaxError, ValueError, RecursionError):
            continue
        changed.update((relative, name) for name in names
                       if old_signatures.get(name, Counter()) != new_signatures.get(name, Counter()))
    check_time(deadline)
    if not changed:
        return None
    listed = "、".join(shown(f"{'/'.join(owners[key])}({key[0]}:{key[1]})") for key in sorted(changed))
    return (f"[harness] 本轮改了字典点名的定义:{listed};未改职责表或总图。"
            "照 docs/rules/harness.md「设计从整体到局部」更新字典。")
