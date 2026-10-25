#!/usr/bin/env python3
"""Name the look-alikes a repo already has for judgment functions this turn wrote."""

from pathlib import Path, PurePosixPath
import re
import subprocess
import time


TURN_BUDGET = 8 * 1024 * 1024
TIME_BUDGET = 1.5
TWIN_LIMIT = 8
FUNCTION_LIMIT = 3
# Longer lines are minified code, and the patterns below get quadratic on them.
LINE_LIMIT = 400
CODE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
# Test folders, and .scratch, which holds specs and archived third-party scripts rather than code.
TEST_DIRS = {"tests", "test", "__tests__"}
JUDGMENT_WORDS = {
    "same", "match", "matches", "matching", "matched", "key", "keys", "normalize", "normalized",
    "normalise", "norm", "identity", "ident", "canonical", "canon", "equal", "equals", "eq",
    "equivalent", "compare", "cmp", "alias",
}
# A name led by one of these does something to records (list, save, fetch, render …) rather than
# decide whether two things are the same; such names are no judgment, and the verbs are no nouns.
ACTION_VERBS = {
    "list", "create", "update", "delete", "remove", "save", "store", "clear", "import", "export",
    "replace", "revoke", "rotate", "confirm", "unlink", "link", "review", "toggle", "record",
    "persist", "fetch", "load", "read", "write", "send", "handle", "on", "render", "show",
    "format", "parse", "verify", "validate", "ensure", "sanitize", "apply", "get", "set", "find",
    "lookup", "iter", "resolve", "count",
}
# A "key" next to one of these is a credential, keyboard or storage key, not an identity key.
KEY_CONTEXTS = {
    "api", "secret", "token", "access", "master", "private", "public", "auth", "license",
    "down", "up", "press", "keyboard", "hotkey", "shortcut",
    "sort", "cache", "storage", "queue", "lock", "config", "setting", "settings", "env", "session",
    "idempotency", "local",
}
STOP_WORDS = {
    "is", "are", "has", "have", "get", "set", "to", "of", "by", "for", "from", "in", "on", "at",
    "as", "with", "into", "the", "an", "and", "or", "not", "can", "should", "make", "build",
    "check", "find", "value", "values", "text", "str", "string", "raw", "new", "old", "default",
    "data", "item", "items", "obj", "args", "input", "helper", "util",
} | ACTION_VERBS
NAME = r"[A-Za-z_$][\w$]*"
PARAMS = r"\((?:[^()]|\([^()]*\))*\)"
PYTHON = (re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*[(\[]"),)
SCRIPT = (
    # function name(…)
    re.compile(rf"\bfunction\b\s*\*?\s*({NAME})\s*[<(]"),
    # name = (…) =>, name = x =>, name = function; params may run onto the next lines.
    re.compile(rf"(?<![\w$])(?<!type )({NAME})\s*(?::[^=]*)?=\s*(?:async\b\s*)?"
               rf"(?:function\b|{NAME}\s*=>|(?:<[^<>]*>\s*)?{PARAMS}\s*(?::[^=]*)?=>|\(\s*$)"),
    # Class and object-literal methods: name(…) {
    re.compile(rf"^\s*(?:(?:public|private|protected|static|async|override|readonly|abstract|get|set)\s+)*"
               rf"\*?\s*({NAME})\s*(?:<[^<>]*>\s*)?\((?:[^;()]|\([^;()]*\))*\)\s*(?::[^;{{}}=]*)?\{{"),
)
KEYWORDS = {"if", "for", "while", "switch", "catch", "with", "function", "return", "else", "do",
            "try", "typeof", "await", "new", "super", "yield", "delete", "void", "case", "throw"}


def git(cwd, deadline, *args):
    """Run one read-only git command inside the time budget; its stdout, or None when git fails."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("judgment twin check ran out of time")
    result = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, timeout=remaining)
    return result.stdout.decode("utf-8", errors="replace") if result.returncode == 0 else None


def code_file(relative):
    """A source file the check reads: a code suffix, outside non-code directories, and not a test by directory or name."""
    from stop_evidence import excluded_dir

    path = PurePosixPath(relative)
    name = path.name
    return (path.suffix in CODE_SUFFIXES
            and not any(excluded_dir(part) or part in TEST_DIRS for part in path.parts[:-1])
            and not (path.suffix == ".py" and (name.startswith("test_") or name.endswith("_test.py")))
            and ".test." not in name and "-test." not in name and ".spec." not in name)


def definitions(text, suffix):
    """List (line number, name) of function definitions in code text, at most one per line."""
    patterns = PYTHON if suffix == ".py" else SCRIPT
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        if len(line) > LINE_LIMIT:
            continue
        for pattern in patterns:
            match = pattern.search(line)
            if match and match.group(1) not in KEYWORDS:
                found.append((number, match.group(1)))
                break
    return found


def name_words(name):
    """Split snake_case and camelCase into lower-case words."""
    return [word.lower() for word in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", name)]


def judgment_like(words):
    """Whether a name's words read as a judgment.

    It needs a judgment word, must not be led by an action verb or test, and a key alone must not
    be a credential, keyboard or storage key.
    """
    judged = {word for word in words if word in JUDGMENT_WORDS}
    if not judged or words[0] in ACTION_VERBS or words[0] == "test":
        return False
    return not (judged <= {"key", "keys"} and not KEY_CONTEXTS.isdisjoint(words))


def judgment_nouns(name):
    """Nouns of a judgment-like name; empty when it is no judgment or has no noun."""
    words = name_words(name)
    if not judgment_like(words):
        return set()
    return {word for word in words
            if word not in JUDGMENT_WORDS and word not in STOP_WORDS and len(word) > 1 and not word.isdigit()}


def shown(text):
    """Escape control and line-break characters so a path or name stays inside its one reminder line."""
    return "".join(char if char.isprintable() else repr(char)[1:-1] for char in text)


def locate(value, roots):
    """Return (file, worktree root, path inside it) for an absolute path in one of the repo's worktrees."""
    if not isinstance(value, str) or not Path(value).is_absolute():
        return None
    path = Path(value).resolve()
    for root in roots:
        if path.is_relative_to(root):
            return path, root, path.relative_to(root).as_posix()
    return None


def new_functions(payload, roots, deadline):
    """List (file, relative path, name) of definitions this turn's successful edits added, in order."""
    from stop_evidence import session_records, successful_edits

    transcript, *subagents = session_records(payload["transcript_path"])
    edits, start = successful_edits(transcript, tail=TURN_BUDGET, turn=True, deadline=deadline)
    if start is not None:
        for source in subagents:
            if time.monotonic() >= deadline:
                raise TimeoutError("judgment twin check ran out of time")
            # A subagent counts only for what it did after this turn opened.
            if source.stat().st_mtime_ns >= start:
                edits.extend(edit for edit in successful_edits(source, tail=TURN_BUDGET, deadline=deadline)[0]
                             if edit[0] is not None and edit[0] >= start)
    found = []
    seen = set()
    for _, tool, data in edits:
        if time.monotonic() >= deadline:
            raise TimeoutError("judgment twin check ran out of time")
        # (path, new text, old text); old None means the version in HEAD.
        pieces = []
        if tool == "FileChange":
            for path, change in data.items():
                if not isinstance(change, dict):
                    continue
                if change.get("type") == "add" and isinstance(change.get("content"), str):
                    pieces.append((path, change["content"], ""))
                elif change.get("type") == "update" and isinstance(change.get("unified_diff"), str):
                    lines = change["unified_diff"].splitlines()
                    pieces.append((change.get("move_path") or path,
                                   "\n".join(line[1:] for line in lines if line.startswith("+")),
                                   "\n".join(line[1:] for line in lines if line.startswith("-"))))
        elif tool in ("Edit", "MultiEdit"):
            changes = [data] if tool == "Edit" else data.get("edits")
            for change in changes if isinstance(changes, list) else ():
                if isinstance(change, dict):
                    pieces.append((data.get("file_path"), change.get("new_string"), change.get("old_string")))
        elif tool == "Write":
            pieces.append((data.get("file_path"), data.get("content"), None))
        for path, new, old in pieces:
            located = locate(path, roots)
            if located is None or not isinstance(new, str) or not code_file(located[2]):
                continue
            path, root, relative = located
            if old is None:
                old = git(root, deadline, "cat-file", "-p", f"HEAD:{relative}") or ""
            suffix = PurePosixPath(relative).suffix
            before = {name for _, name in definitions(old if isinstance(old, str) else "", suffix)}
            for _, name in definitions(new, suffix):
                if name not in before and (path, name) not in seen:
                    seen.add((path, name))
                    found.append((path, relative, name))
    return found


def twins(top, nouns, own, deadline):
    """List (path, line, name) of judgment-like definitions in the repo sharing a noun, except own.

    Every file's first twin comes before any file's second, public names first within a round:
    the copy a session misses sits in another area, and one file's helpers would fill the list.
    """
    output = git(top, deadline, "-c", "core.quotePath=false", "grep", "-n", "-z", "-I", "-i", "-F",
                 *(arg for noun in sorted(nouns) for arg in ("-e", noun)),
                 "--", *(f"*{suffix}" for suffix in sorted(CODE_SUFFIXES)))
    found = []
    for record in (output or "").split("\n"):
        parts = record.split("\0", 2)
        if len(parts) != 3 or not parts[1].isdigit() or not code_file(parts[0]):
            continue
        path, number, text = parts
        for _, name in definitions(text, PurePosixPath(path).suffix):
            words = name_words(name)
            if not nouns.isdisjoint(words) and judgment_like(words) and (path, name) != own:
                found.append((path, int(number), name))
    # Public names are the ones meant to be called from elsewhere.
    found.sort(key=lambda twin: twin[2].startswith("_"))
    rounds = {}
    ranked = []
    for twin in found:
        rounds[twin[0]] = rounds.get(twin[0], 0) + 1
        ranked.append((rounds[twin[0]], twin))
    return [twin for _, twin in sorted(ranked, key=lambda pair: pair[0])]


def reminder(payload, cwd, root):
    """One line per judgment-like function this turn wrote that the repo already has twins of, or None.

    Raises TimeoutError or subprocess.TimeoutExpired once the time budget is spent; the
    caller then drops the reminder.
    """
    from session_start import CORE_TABLE, core_judgments

    transcript = payload.get("transcript_path")
    if not isinstance(transcript, str) or not transcript or not Path(transcript).is_file():
        return None
    deadline = time.monotonic() + TIME_BUDGET
    top = (git(cwd, deadline, "rev-parse", "--show-toplevel") or "").strip()
    if not top:
        return None
    top = Path(top).resolve()
    listing = git(top, deadline, "worktree", "list", "--porcelain") or ""
    roots = {top} | {Path(line[len("worktree "):]).resolve()
                     for line in listing.splitlines() if line.startswith("worktree ")}
    # A worktree nested inside another one owns its files.
    roots = sorted(roots, key=lambda path: len(path.parts), reverse=True)
    lines = []
    for path, relative, name in new_functions(payload, roots, deadline):
        if len(lines) >= FUNCTION_LIMIT:
            break
        nouns = judgment_nouns(name)
        if not nouns:
            continue
        found = twins(top, nouns, (relative, name), deadline)
        if not found:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            number = next((line for line, defined in definitions(text, path.suffix) if defined == name), None)
        except OSError:
            number = None
        where = shown(relative if number is None else f"{relative}:{number}")
        listed = "、".join(shown(f"{twin}:{line} {defined}") for twin, line, defined in found[:TWIN_LIMIT])
        lines.append(
            f"[harness] 本轮新写的 {shown(name)}({where})像一个判断,库里已有同类:{listed}(共 {len(found)} 个)。"
            "能复用就调用;现成的有毛病就修它;意思本来不同就另起名字、写理由"
            "(docs/rules/harness.md「核心判断只写一份」)。"
        )
    if not lines:
        return None
    if core_judgments(root):
        lines[-1] += f"先对照 {CORE_TABLE}。"
    return "\n".join(lines)
