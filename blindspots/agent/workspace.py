"""The task's repository, as the agent sees it (Week 2 step 3, decision 1).

The code comes out of the task's own SWE-bench Docker image, from /testbed
[PRIMARY — swebench 5.0.2 source], which is where the harness later applies
and tests the patch. So the agent reads exactly the code it will be judged
on, and no network is needed: the dev images are already local.

    ws = prepare(task, root=Path.home() / "bs-work" / "repos")

A copy is kept per task and reused, but only after re-checking that its
HEAD is the task's base_commit.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_IN_IMAGE = "/testbed"


class WorkspaceError(RuntimeError):
    """The repository could not be prepared, or is not at the right commit."""


@dataclass(frozen=True)
class Task:
    """What the agent may see (issue, commit, image) and, separately, the gold
    patch, which is only ever read AFTER a run, for the localisation
    diagnostic. hints_text is deliberately not carried: the standard
    SWE-bench setting gives the agent the problem statement only."""

    instance_id: str
    repo: str
    base_commit: str
    image: str
    problem_statement: str
    gold_patch: str

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Task:
        return cls(instance_id=row["instance_id"], repo=row["repo"],
                   base_commit=row["base_commit"], image=row["image"],
                   problem_statement=row["problem_statement"], gold_patch=row["patch"])


def load_task(instance_id: str, dataset: str = "SWE-bench/SWE-bench_Verified") -> Task:
    """Read one task from the cached dataset. Set HF_DATASETS_OFFLINE=1 first."""
    from datasets import load_dataset  # late import: slow, and needs the offline flag

    for row in load_dataset(dataset, split="test"):
        if row["instance_id"] == instance_id:
            return Task.from_row(row)
    raise WorkspaceError(f"{instance_id} not in {dataset}")


def load_tasks(instance_ids: list[str],
               dataset: str = "SWE-bench/SWE-bench_Verified") -> list[Task]:
    """Several tasks in one pass over the dataset, in the order given."""
    from datasets import load_dataset

    wanted = set(instance_ids)
    found = {r["instance_id"]: Task.from_row(r)
             for r in load_dataset(dataset, split="test") if r["instance_id"] in wanted}
    missing = wanted - found.keys()
    if missing:
        raise WorkspaceError(f"not in {dataset}: {sorted(missing)}")
    return [found[i] for i in instance_ids]


def _run(*cmd: str, cwd: Path | None = None) -> str:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if p.returncode != 0:
        raise WorkspaceError(f"{' '.join(cmd)} failed: {p.stderr.strip()[:300]}")
    return p.stdout.strip()


def head_commit(repo_dir: Path) -> str:
    return _run("git", "-C", str(repo_dir), "rev-parse", "HEAD")


def prepare(task: Task, root: Path) -> Path:
    """Return a local copy of the task's code, exactly as the harness tests it:
    base_commit plus, at most, the image's packaging and test-configuration
    edits (environment_changes)."""
    dest = Path(root) / task.instance_id
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        # `docker create` makes a stopped container: nothing runs, we only
        # copy files out of it, then remove it.
        cid = _run("docker", "create", task.image)
        try:
            _run("docker", "cp", f"{cid}:{REPO_IN_IMAGE}", str(dest))
        finally:
            subprocess.run(["docker", "rm", cid], capture_output=True)
        # The image's copy may already differ from the commit (environment
        # setup can touch files) [UNVERIFIED]. Remember its state as copied,
        # so a later reuse can check that nothing has changed since.
        (dest / ".git" / "blindspots-baseline").write_text(_status(dest))
    environment_changes(task, dest)  # refuses if the image changed real code
    baseline = (dest / ".git" / "blindspots-baseline").read_text()
    if _status(dest) != baseline:
        raise WorkspaceError(f"{dest} changed since it was copied; delete it to re-copy")
    return dest


# Files SWE-bench's image build may change on top of base_commit, to make an
# old project install and to make pytest report every test (results entry #8:
# sphinx-8621 pins dependencies in setup.py and adds -rA in tox.ini; django
# images add an empty commit). Anything else changed means the image's code
# is not the task's code, and the task is refused.
ENVIRONMENT_FILES = {"setup.py", "setup.cfg", "tox.ini", "pyproject.toml", "pytest.ini"}


def _is_environment_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return path in ENVIRONMENT_FILES or (
        "/" not in path and name.startswith("requirements") and name.endswith(".txt"))


def environment_changes(task: Task, repo_dir: Path) -> list[str]:
    """Files the image changed on top of base_commit. [] for an identical tree.

    The agent sees the image's tree, because that is what the harness tests.
    Refuses unless base_commit is an ancestor of HEAD and every changed file
    is packaging or test configuration (ENVIRONMENT_FILES), at the top level.
    """
    d = str(repo_dir)
    try:
        _run("git", "-C", d, "cat-file", "-e", f"{task.base_commit}^{{commit}}")
    except WorkspaceError:
        raise WorkspaceError(f"{repo_dir} does not contain base_commit {task.base_commit[:12]}")
    ancestor = subprocess.run(["git", "-C", d, "merge-base", "--is-ancestor",
                               task.base_commit, "HEAD"], capture_output=True)
    if ancestor.returncode != 0:
        raise WorkspaceError(f"{repo_dir}: base_commit {task.base_commit[:12]} is not an "
                             f"ancestor of HEAD ({head_commit(repo_dir)[:12]})")
    changed = content_changes(repo_dir, task.base_commit)
    code = [f for f in changed if not _is_environment_file(f)]
    if code:
        shown = ", ".join(code[:10]) + (f" ... and {len(code) - 10} more" if len(code) > 10 else "")
        raise WorkspaceError(f"{repo_dir}: files at HEAD ({head_commit(repo_dir)[:12]}) differ "
                             f"from base_commit {task.base_commit[:12]} beyond packaging "
                             f"and test configuration: {shown}")
    return changed


def content_changes(repo_dir: Path, base_commit: str) -> list[str]:
    """Files whose CONTENTS differ between base_commit and HEAD.

    A change of permissions alone is ignored. SWE-bench's image build runs
    `chmod -R 777` on the repository [PRIMARY — swebench 5.0.2
    image_builder/docker_utils.py]; when that is committed, every file shows
    as changed while no byte of code differs (results entry #8, django-14017).
    `git diff --raw` gives each file's content id (blob hash) before and after;
    equal ids mean equal bytes.
    """
    out = subprocess.run(["git", "-C", str(repo_dir), "diff", "--raw", "-z", "--no-renames",
                          "--abbrev=40", base_commit, "HEAD"],
                         capture_output=True, text=True, check=True).stdout
    # -z output: ":oldmode newmode oldblob newblob status\0path\0" per file
    parts = out.split("\0")
    changed = []
    for meta, path in zip(parts[0::2], parts[1::2]):
        if not meta:
            continue
        _, _, old_blob, new_blob, _ = meta.lstrip(":").split(" ")
        if old_blob != new_blob:
            changed.append(path)
    return sorted(changed)


def _status(repo_dir: Path) -> str:
    return _run("git", "-C", str(repo_dir), "status", "--porcelain", "--untracked-files=no")


def repo_files(repo_dir: Path) -> list[str]:
    """Every tracked file, as a repo-relative path. `git ls-files` rather than
    a directory walk, so build output and caches are never shown."""
    return sorted(_run("git", "-C", str(repo_dir), "ls-files").splitlines())
