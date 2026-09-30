"""Choose which files the agent sees (Week 2 step 3, decision 4).

Keyword matching on the issue text ONLY. The gold patch is never read here;
it would leak where the bug is (the SWE-bench paper's "oracle" setting).

Signals, strongest first:
  1. a file path written in the issue            "django/db/models/query.py"
  2. a dotted module name, turned into a path    "django.db.models.query"
  3. a bare file name that exists in the repo    "query.py"
  4. a class or function the issue names, found by its definition
     ("class QuerySet", "def bulk_create") in a Python file
Test files are ranked below source files. Files go in, best first, until
the content budget is used. Deterministic: same issue and repo, same files.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

CONTENT_BUDGET_BYTES = 120_000
TREE_BUDGET_BYTES = 20_000
MAX_FILES = 8

W_PATH, W_MODULE, W_FILENAME, W_DEFINITION = 100.0, 80.0, 30.0, 10.0
TEST_FACTOR = 0.3

_PATH = re.compile(r"[\w.\-]+(?:/[\w.\-]+)+\.\w+|[\w\-]+\.py\b")
_DOTTED = re.compile(r"\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+\b")
_WORD = re.compile(r"\b[A-Za-z_]\w{2,}\b")
_DEF = re.compile(r"^\s*(?:class|def|async\s+def)\s+([A-Za-z_]\w*)", re.MULTILINE)

# Too common to say anything about location.
_STOP = {"self", "None", "True", "False", "the", "and", "for", "not", "with", "this",
         "that", "from", "import", "return", "class", "def", "print", "value", "name",
         "data", "type", "test", "tests", "args", "kwargs", "object", "list", "dict",
         "str", "int", "get", "set", "init", "__init__", "main", "run", "call"}


def identifiers(issue: str) -> set[str]:
    """Words that look like code, not English: snake_case, CamelCase, or
    anything inside `backticks` or an indented/fenced code line. Plain
    lowercase words ("save", "field") are left out; they are defined in
    too many files to say anything about where the bug is."""
    code = " ".join(re.findall(r"`([^`]+)`", issue))
    code += " " + " ".join(l for l in issue.splitlines() if l.startswith(("    ", "\t", ">>>")))
    found = set(_WORD.findall(code))
    for w in _WORD.findall(issue):
        if "_" in w.strip("_") or re.search(r"[a-z][A-Z]|^[A-Z][a-z]+[A-Z]", w):
            found.add(w)
    return found


@dataclass
class Selection:
    files: list[str]                        # chosen, best first
    scores: dict[str, float]                # every candidate that scored
    reasons: dict[str, list[str]]           # why each candidate scored
    skipped_for_budget: list[str] = field(default_factory=list)
    content_bytes: int = 0


def is_test(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return any(p in ("tests", "test", "testing") for p in parts[:-1]) or \
        PurePosixPath(path).name.startswith("test_")


def select(repo_dir: Path, files: list[str], issue: str, *,
           budget: int = CONTENT_BUDGET_BYTES, max_files: int = MAX_FILES) -> Selection:
    score: dict[str, float] = defaultdict(float)
    why: dict[str, list[str]] = defaultdict(list)
    fileset = set(files)

    def add(path: str, w: float, reason: str) -> None:
        score[path] += w
        why[path].append(reason)

    # 1. explicit paths (also matched as a suffix: "db/models/query.py")
    for m in set(_PATH.findall(issue)):
        m = m.strip("./")
        hits = [f for f in files if f == m or f.endswith("/" + m)]
        if "/" in m and hits:
            for f in hits:
                add(f, W_PATH / len(hits), f"path {m}")
        elif hits:  # 3. bare file name: weaker, split between same-named files
            for f in hits:
                add(f, W_FILENAME / len(hits), f"file name {m}")

    # 2. dotted module names: a.b.c -> a/b/c.py or a/b/c/__init__.py,
    #    trying shorter prefixes when the last part is a class or function
    for m in set(_DOTTED.findall(issue)):
        parts = m.split(".")
        for n in range(len(parts), 1, -1):
            base = "/".join(parts[:n])
            hit = next((c for c in (base + ".py", base + "/__init__.py") if c in fileset), None)
            if hit:
                add(hit, W_MODULE, f"module {m}")
                break

    # 4. names the issue mentions that some Python file defines
    words = {w for w in identifiers(issue) if w not in _STOP}
    if words:
        for f in files:
            if not f.endswith(".py"):
                continue
            try:
                text = (repo_dir / f).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            defined = set(_DEF.findall(text)) & words
            for name in sorted(defined):
                add(f, W_DEFINITION, f"defines {name}")

    for f in list(score):
        if is_test(f):
            score[f] *= TEST_FACTOR

    ranked = sorted(score, key=lambda f: (-score[f], f))
    sel = Selection(files=[], scores=dict(score), reasons=dict(why))
    for f in ranked:
        if len(sel.files) >= max_files:
            break
        size = (repo_dir / f).stat().st_size
        if sel.content_bytes + size > budget:
            sel.skipped_for_budget.append(f)
            continue
        sel.files.append(f)
        sel.content_bytes += size
    return sel


def tree(files: list[str], selected: list[str], *, budget: int = TREE_BUDGET_BYTES) -> str:
    """The files in each chosen file's directory (one level, not recursive).

    Enough to show the neighbourhood of the likely bug without listing the
    whole repository. Cut off at the budget, with a marker saying so.
    """
    dirs = sorted({str(PurePosixPath(f).parent) for f in selected})
    lines: list[str] = []
    used = 0
    for d in dirs:
        members = [f for f in files if str(PurePosixPath(f).parent) == d]
        for line in [f"{d}/"] + [f"  {PurePosixPath(f).name}" for f in members]:
            if used + len(line) + 1 > budget:
                lines.append("  ... (listing cut off)")
                return "\n".join(lines)
            lines.append(line)
            used += len(line) + 1
    return "\n".join(lines)


def gold_files(gold_patch: str) -> list[str]:
    """Files a patch changes. For the after-run diagnostic ONLY."""
    return sorted(set(re.findall(r"^diff --git a/(\S+) b/", gold_patch, re.MULTILINE)))


def localisation(gold_patch: str, selected: list[str]) -> dict:
    """Were the files the gold patch changes among those shown? Computed after
    the run and stored in the record; never fed back into any prompt."""
    gold = gold_files(gold_patch)
    shown = [g for g in gold if g in selected]
    return {"gold_files": gold, "gold_files_shown": shown,
            "all_gold_files_shown": bool(gold) and len(shown) == len(gold)}
