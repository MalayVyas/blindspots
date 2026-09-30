"""Search/replace blocks in, a correct unified diff out (step 3, decision 2).

The model quotes the exact lines it wants to change and gives their
replacement. Our code, not the model, writes the diff, so a wrong line
number or a malformed hunk header can never be the reason a fix fails.

The format the prompt asks for:

    path/to/file.py
    <<<<<<< SEARCH
    exact existing lines
    =======
    replacement lines
    >>>>>>> REPLACE

An empty SEARCH section creates a new file (the file must not exist yet).

Strict matching: the SEARCH text must appear exactly once in the file, as
it stands after any earlier blocks. Zero matches or several matches is an
EditError; the runner records it as patch_apply_failed, a counted failure.
No fuzzy matching: a guess about what the model meant would be a guess we
then score.
"""

from __future__ import annotations

import difflib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

_BLOCK = re.compile(
    r"^(?P<path>[^\n`<>=]+?)[ \t]*\n"
    r"(?:```[^\n]*\n)?"
    r"<<<<<<< SEARCH[ \t]*\n(?P<search>.*?)^=======[ \t]*\n(?P<replace>.*?)^>>>>>>> REPLACE[ \t]*$",
    re.DOTALL | re.MULTILINE,
)


class EditError(ValueError):
    """The model's edits cannot be applied as written."""


@dataclass(frozen=True)
class Edit:
    path: str
    search: str
    replace: str


def parse(reply: str) -> list[Edit]:
    """Every block in the reply, in order. No blocks means no edit."""
    edits = []
    for m in _BLOCK.finditer(reply):
        path = m.group("path").strip().strip("`").strip()
        edits.append(Edit(path=path, search=m.group("search"), replace=m.group("replace")))
    return edits


def _safe_path(repo_dir: Path, path: str) -> Path:
    p = PurePosixPath(path)
    if p.is_absolute() or ".." in p.parts or not p.parts or p.parts[0] == ".git":
        raise EditError(f"path outside the repository: {path!r}")
    return repo_dir / p


def apply(repo_dir: Path, edits: list[Edit]) -> dict[str, tuple[str | None, str]]:
    """Apply edits in memory. Returns {path: (original or None if new, new text)}.

    Nothing is written to disk: the repository copy stays clean for reuse.
    """
    state: dict[str, tuple[str | None, str]] = {}
    for i, e in enumerate(edits, 1):
        full = _safe_path(repo_dir, e.path)
        if e.path in state:
            original, current = state[e.path]
        elif full.is_file():
            original = current = full.read_text(encoding="utf-8")
        else:
            original, current = None, ""

        if e.search == "":
            if original is not None or current:
                raise EditError(f"block {i}: empty SEARCH but {e.path} already exists")
            state[e.path] = (None, e.replace)
            continue
        if original is None and e.path not in state:
            raise EditError(f"block {i}: {e.path} does not exist")
        # A block's text always ends in a newline, so the last line of a file
        # that has no final newline could never match. Compare as if the
        # newline were there, and leave it off again afterwards.
        missing_nl = bool(current) and not current.endswith("\n")
        text = current + "\n" if missing_nl else current
        n = text.count(e.search)
        if n == 0:
            raise EditError(f"block {i}: SEARCH text not found in {e.path}")
        if n > 1:
            raise EditError(f"block {i}: SEARCH text appears {n} times in {e.path}; "
                            "it must identify one place")
        new = text.replace(e.search, e.replace, 1)
        if missing_nl and new.endswith("\n"):
            new = new[:-1]
        state[e.path] = (original, new)
    return state


def _lines(text: str) -> list[str]:
    """Split keeping line ends, and mark a missing final newline the way
    diff does, so git can apply the patch exactly."""
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n\\ No newline at end of file\n"
    return lines


def to_diff(changes: dict[str, tuple[str | None, str]]) -> str:
    """A unified diff in `git diff` format, which the harness applies with
    `git apply` [PRIMARY — swebench 5.0.2 run_evaluation.py]."""
    out = []
    for path in sorted(changes):
        original, new = changes[path]
        if original == new:
            continue
        header = [f"diff --git a/{path} b/{path}\n"]
        if original is None:
            header.append("new file mode 100644\n")
        body = list(difflib.unified_diff(
            _lines(original or ""), _lines(new),
            fromfile="/dev/null" if original is None else f"a/{path}",
            tofile=f"b/{path}", n=3))
        out.extend(header + body)
    return "".join(out)


def check_applies(repo_dir: Path, diff: str) -> str | None:
    """`git apply --check` against the real repository copy. None if the diff
    applies; otherwise git's message. A failure here is our bug, not the
    model's, because we wrote the diff: so it is checked every time."""
    if not diff:
        return None
    p = subprocess.run(["git", "-C", str(repo_dir), "apply", "--check", "-"],
                       input=diff, capture_output=True, text=True)
    return None if p.returncode == 0 else p.stderr.strip()
