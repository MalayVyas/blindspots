"""Step 3 agent tests: a tiny real git repository, a fake model. $0."""

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from blindspots.accountant import Accountant, Limits
from blindspots.agent import context as ctx
from blindspots.agent import edits, simple
from blindspots.agent.workspace import Task, WorkspaceError, prepare, repo_files
from blindspots.providers.deepseek import build_request, parse_response

CALC = '''def add_numbers(a, b):
    return a - b


def mul(a, b):
    return a * b
'''


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "mypkg" / "tests").mkdir(parents=True)
    (r / "mypkg" / "__init__.py").write_text("")
    (r / "mypkg" / "calc.py").write_text(CALC)
    (r / "mypkg" / "util.py").write_text("def helper():\n    return 1\n")
    (r / "mypkg" / "tests" / "test_calc.py").write_text(
        "from mypkg.calc import add_numbers\n\ndef test_add():\n    assert add_numbers(1, 2) == 3\n")
    (r / "README").write_text("no trailing newline")
    git(r, "init", "-q")
    git(r, "-c", "user.email=t@t", "-c", "user.name=t", "add", ".")
    git(r, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return r


ISSUE = "`add_numbers` in mypkg/calc.py subtracts instead of adding.\n"
GOLD = "diff --git a/mypkg/calc.py b/mypkg/calc.py\n--- a/mypkg/calc.py\n+++ b/mypkg/calc.py\n"


def task(repo_dir, issue=ISSUE):
    head = subprocess.run(["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    return Task(instance_id="t-1", repo="me/mypkg", base_commit=head, image="none",
                problem_statement=issue, gold_patch=GOLD)


class FakeModel:
    def __init__(self, reply):
        self.reply, self.seen = reply, []

    def complete(self, messages, *, model, max_tokens, temperature, thinking,
                 reasoning_effort=None, timeout_s=None):
        self.seen.append(messages)
        body = build_request(messages, model=model, max_tokens=max_tokens,
                             temperature=temperature, thinking=thinking)
        data = {"model": model, "choices": [{"message": {"content": self.reply},
                                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 500, "completion_tokens": 60,
                          "prompt_tokens_details": {"prompt_cache_hit_tokens": 0,
                                                    "prompt_cache_miss_tokens": 500}}}
        return parse_response(data, request=body, model=model,
                              started_at=datetime(2026, 10, 3, tzinfo=timezone.utc),
                              latency_s=1.0)


GOOD_REPLY = """The function subtracts.

mypkg/calc.py
<<<<<<< SEARCH
def add_numbers(a, b):
    return a - b
=======
def add_numbers(a, b):
    return a + b
>>>>>>> REPLACE
"""


# ---------------------------------------------------------------- selection

def test_path_in_issue_wins_and_tests_rank_lower(repo):
    sel = ctx.select(repo, repo_files(repo), ISSUE)
    assert sel.files[0] == "mypkg/calc.py"
    assert sel.scores["mypkg/calc.py"] > sel.scores.get("mypkg/tests/test_calc.py", 0)
    assert "mypkg/util.py" not in sel.files        # nothing points at it


def test_dotted_module_and_definition_signals(repo):
    sel = ctx.select(repo, repo_files(repo), "Calling mypkg.calc.mul is fine but `helper` breaks")
    assert "mypkg/calc.py" in sel.files and "mypkg/util.py" in sel.files
    assert any(r.startswith("module") for r in sel.reasons["mypkg/calc.py"])
    assert sel.reasons["mypkg/util.py"] == ["defines helper"]


def test_plain_english_words_do_not_select_files(repo):
    assert ctx.identifiers("the helper function is broken") == set()
    assert "helper" in ctx.identifiers("the `helper` function is broken")
    assert {"add_numbers", "QuerySet"} <= ctx.identifiers("add_numbers and QuerySet")


def test_budget_skips_files_that_do_not_fit(repo):
    sel = ctx.select(repo, repo_files(repo), ISSUE, budget=10)
    assert sel.files == [] and "mypkg/calc.py" in sel.skipped_for_budget


def test_tree_lists_only_chosen_directories(repo):
    t = ctx.tree(repo_files(repo), ["mypkg/calc.py"])
    assert t.splitlines()[0] == "mypkg/" and "  util.py" in t and "README" not in t
    assert "listing cut off" in ctx.tree(repo_files(repo), ["mypkg/calc.py"], budget=20)


def test_localisation_diagnostic():
    assert ctx.localisation(GOLD, ["mypkg/calc.py"])["all_gold_files_shown"]
    assert not ctx.localisation(GOLD, ["mypkg/util.py"])["all_gold_files_shown"]


# ---------------------------------------------------------------- edits

def test_parse_ignores_prose_and_fences():
    reply = "Here:\n\n```python\nmypkg/calc.py\n<<<<<<< SEARCH\nx\n=======\ny\n>>>>>>> REPLACE\n```\n"
    [e] = edits.parse(reply)
    assert (e.path, e.search, e.replace) == ("mypkg/calc.py", "x\n", "y\n")


def test_diff_applies_and_gives_the_intended_file(repo):
    changes = edits.apply(repo, edits.parse(GOOD_REPLY))
    diff = edits.to_diff(changes)
    assert edits.check_applies(repo, diff) is None
    subprocess.run(["git", "-C", str(repo), "apply", "-"], input=diff, text=True, check=True)
    assert "return a + b" in (repo / "mypkg/calc.py").read_text()


def test_last_line_of_file_without_final_newline_can_be_edited(repo):
    reply = "README\n<<<<<<< SEARCH\nno trailing newline\n=======\nfixed\n>>>>>>> REPLACE\n"
    changes = edits.apply(repo, edits.parse(reply))
    assert changes["README"][1] == "fixed"                 # still no final newline
    diff = edits.to_diff(changes)
    assert "No newline at end of file" in diff
    assert edits.check_applies(repo, diff) is None
    subprocess.run(["git", "-C", str(repo), "apply", "-"], input=diff, text=True, check=True)
    assert (repo / "README").read_text() == "fixed"


def test_new_file_and_sequential_edits(repo):
    reply = ("mypkg/new.py\n<<<<<<< SEARCH\n=======\nX = 1\n>>>>>>> REPLACE\n"
             "mypkg/calc.py\n<<<<<<< SEARCH\n    return a - b\n=======\n    return a + b\n>>>>>>> REPLACE\n"
             "mypkg/calc.py\n<<<<<<< SEARCH\n    return a + b\n=======\n    return b + a\n>>>>>>> REPLACE\n")
    diff = edits.to_diff(edits.apply(repo, edits.parse(reply)))
    assert "new file mode" in diff and "+    return b + a" in diff
    assert edits.check_applies(repo, diff) is None


@pytest.mark.parametrize("reply, message", [
    ("mypkg/calc.py\n<<<<<<< SEARCH\nnot there\n=======\nx\n>>>>>>> REPLACE\n", "not found"),
    ("mypkg/calc.py\n<<<<<<< SEARCH\n(a, b):\n=======\nx\n>>>>>>> REPLACE\n", "2 times"),
    ("../etc/passwd\n<<<<<<< SEARCH\nx\n=======\ny\n>>>>>>> REPLACE\n", "outside"),
    ("mypkg/nope.py\n<<<<<<< SEARCH\nx\n=======\ny\n>>>>>>> REPLACE\n", "does not exist"),
    ("mypkg/calc.py\n<<<<<<< SEARCH\n=======\ny\n>>>>>>> REPLACE\n", "already exists"),
])
def test_bad_edits_are_errors_not_guesses(repo, reply, message):
    with pytest.raises(edits.EditError, match=message):
        edits.apply(repo, edits.parse(reply))


def test_apply_never_writes_to_disk(repo):
    edits.apply(repo, edits.parse(GOOD_REPLY))
    assert (repo / "mypkg/calc.py").read_text() == CALC


# ---------------------------------------------------------------- the agent

def run(repo, reply, issue=ISSUE):
    model = FakeModel(reply)
    acct = Accountant(model, Limits(), model="deepseek-flash")
    return simple.solve(task(repo, issue), repo, acct), model, acct


def test_solve_end_to_end(repo):
    res, model, acct = run(repo, GOOD_REPLY)
    assert res.status == "patch" and res.error is None
    assert "+    return a + b" in res.patch
    assert res.selection["files"][0] == "mypkg/calc.py"
    assert res.diagnostics["localisation"]["all_gold_files_shown"]
    assert set(res.prompt_hashes) == {f"simple/{p}" for p in simple.PARTS}
    assert acct.usage().model_calls == 1


def test_prompt_layout_stable_parts_first(repo):
    _, model, _ = run(repo, GOOD_REPLY)
    [msgs] = model.seen
    assert [m["role"] for m in msgs] == ["system", "user", "user", "user"]
    assert "### FILE: mypkg/calc.py" in msgs[1]["content"]
    assert ISSUE.strip() in msgs[2]["content"]
    assert msgs[3]["content"] == simple.load_prompts()["instruction"]   # role part last, verbatim
    # Same task twice: identical messages, so the whole prefix can be cached.
    _, model2, _ = run(repo, GOOD_REPLY)
    assert model2.seen[0] == msgs


def test_braces_in_issue_survive(repo):
    _, model, _ = run(repo, GOOD_REPLY, issue=ISSUE + "dict {'a': 1} and {tree}\n")
    assert "{'a': 1} and {tree}" in model.seen[0][2]["content"]


@pytest.mark.parametrize("reply, status", [
    ("I am not sure what to change.", "no_edits"),
    ("mypkg/calc.py\n<<<<<<< SEARCH\nnope\n=======\nx\n>>>>>>> REPLACE\n", "edit_failed"),
])
def test_unusable_replies_give_no_patch(repo, reply, status):
    res, _, _ = run(repo, reply)
    assert res.status == status and res.patch == "" and res.reply == reply


def test_workspace_refuses_wrong_commit(repo, tmp_path):
    t = task(repo)
    root = tmp_path / "ws"
    (root).mkdir()
    subprocess.run(["cp", "-r", str(repo), str(root / t.instance_id)], check=True)
    (root / t.instance_id / ".git" / "blindspots-baseline").write_text("")
    assert prepare(t, root) == root / t.instance_id
    bad = Task(**{**t.__dict__, "base_commit": "0" * 40})
    with pytest.raises(WorkspaceError, match="does not contain"):
        prepare(bad, root)
    ws = root / t.instance_id
    # An empty commit on top (what SWE-bench images have) is accepted...
    git(ws, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "SWE-bench")
    assert prepare(t, root) == ws
    # ...so is one that only changes packaging / test configuration (the
    # sphinx images pin dependencies in setup.py and add -rA in tox.ini)...
    from blindspots.agent.workspace import environment_changes
    (ws / "setup.py").write_text("install_requires = ['Jinja2<3.0']\n")
    (ws / "tox.ini").write_text("[testenv]\ncommands = pytest -rA\n")
    git(ws, "-c", "user.email=t@t", "-c", "user.name=t", "add", "setup.py", "tox.ini")
    git(ws, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "SWE-bench")
    assert prepare(t, root) == ws
    assert environment_changes(t, ws) == ["setup.py", "tox.ini"]
    git(ws, "reset", "-q", "--hard", "HEAD~1")
    # ...so is one that only changes file permissions (the chmod -R 777 in
    # SWE-bench's image build), even on source files...
    (ws / "mypkg" / "calc.py").chmod(0o755)
    (ws / "mypkg" / "util.py").chmod(0o755)
    git(ws, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "SWE-bench")
    (ws / ".git" / "blindspots-baseline").write_text("")
    assert prepare(t, root) == ws
    assert environment_changes(t, ws) == []
    git(ws, "reset", "-q", "--hard", "HEAD~1")
    # ...a commit that changes code is not.
    (ws / "mypkg" / "util.py").write_text("changed\n")
    git(ws, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "edit")
    (ws / ".git" / "blindspots-baseline").write_text("")
    with pytest.raises(WorkspaceError, match=r"beyond packaging.*mypkg/util.py"):
        prepare(t, root)
    git(ws, "reset", "-q", "--hard", "HEAD~1")
    # A HEAD that does not descend from base_commit is refused.
    git(ws, "checkout", "-q", "--orphan", "other")
    git(ws, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "unrelated")
    with pytest.raises(WorkspaceError, match="not an ancestor"):
        prepare(t, root)
    git(ws, "checkout", "-q", "-f", "master" if subprocess.run(
        ["git", "-C", str(ws), "rev-parse", "--verify", "-q", "master"],
        capture_output=True).returncode == 0 else "main")
    (root / t.instance_id / "mypkg" / "calc.py").write_text("changed\n")
    with pytest.raises(WorkspaceError, match="changed since"):
        prepare(t, root)
