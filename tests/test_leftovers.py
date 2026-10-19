import json
import subprocess
from pathlib import Path

import pytest

from git_leftovers.cli import main
from git_leftovers.core import _is_secret, find_repos, inspect


def run(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def commit(repo: Path, name: str, text: str = "x") -> None:
    (repo / name).parent.mkdir(parents=True, exist_ok=True)
    (repo / name).write_text(text)
    run(repo, "add", name)
    run(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", f"add {name}")


@pytest.fixture
def pushed(tmp_path):
    """A clone whose main branch is fully pushed to a bare remote."""
    remote = tmp_path / "remote.git"
    run(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    work = tmp_path / "work" / "project"
    work.parent.mkdir()
    run(work.parent, "clone", "-q", str(remote), "project")
    run(work, "checkout", "-q", "-b", "main")
    commit(work, "README.md")
    run(work, "push", "-q", "-u", "origin", "main")
    return work


def test_clean_repo_has_no_findings(pushed):
    rep = inspect(pushed)
    assert rep.clean, rep.findings
    assert rep.branch == "main" and rep.remotes == ["origin"]


def test_modified_untracked_and_stash(pushed):
    (pushed / "README.md").write_text("changed")
    (pushed / "notes.txt").write_text("new")
    rep = inspect(pushed)
    assert (rep.modified, rep.untracked) == (1, 1)
    run(pushed, "stash", "-q", "--include-untracked")
    rep = inspect(pushed)
    assert rep.stashes == 1 and rep.modified == 0 and rep.untracked == 0


def test_unpushed_commits_on_tracking_branch(pushed):
    commit(pushed, "a.txt")
    commit(pushed, "b.txt")
    assert inspect(pushed).unpushed == {"main": 2}


def test_local_branch_with_new_commits(pushed):
    run(pushed, "checkout", "-q", "-b", "feature")
    commit(pushed, "feature.py")
    rep = inspect(pushed)
    assert rep.unpushed == {"feature": 1}
    assert "branch feature: 1 commit(s), branch not on any remote" in rep.findings


def test_local_branch_without_new_commits_is_fine(pushed):
    run(pushed, "branch", "scratch")
    assert inspect(pushed).clean


def test_repo_without_remote(tmp_path):
    repo = tmp_path / "solo"
    repo.mkdir()
    run(repo, "init", "-q", "-b", "main")
    commit(repo, "main.py")
    rep = inspect(repo)
    assert "no remote: the whole repository exists only here" in rep.findings


def test_secret_in_history_even_after_delete(pushed):
    commit(pushed, ".env", "TOKEN=abc")
    commit(pushed, "config/.env.example", "TOKEN=")
    run(pushed, "rm", "-q", ".env")
    run(pushed, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "remove env")
    run(pushed, "push", "-q")
    rep = inspect(pushed)
    assert rep.secret_files == [".env"]
    assert inspect(pushed, check_history=False).secret_files == []


@pytest.mark.parametrize(
    "name,secret",
    [
        (".env", True),
        ("deploy/.env.production", True),
        (".env.example", False),
        ("certs/server.pem", True),
        ("ebay_credentials.json", True),
        ("src/credentials.py", False),
        ("README.md", False),
    ],
)
def test_secret_patterns(name, secret):
    assert _is_secret(name) is secret


def test_find_repos_skips_dependency_dirs(tmp_path, pushed):
    nested = pushed / "vendor" / "lib"
    nested.mkdir(parents=True)
    run(nested, "init", "-q")
    hidden = pushed / "node_modules" / "pkg"
    hidden.mkdir(parents=True)
    run(hidden, "init", "-q")
    repos = find_repos([tmp_path / "work"])
    assert pushed.resolve() in repos and nested.resolve() in repos
    assert hidden.resolve() not in repos


def test_cli_exit_code_and_json(pushed, capsys):
    assert main([str(pushed.parent)]) == 0
    assert "0 with work that exists only here" in capsys.readouterr().out
    commit(pushed, "wip.py")
    assert main([str(pushed.parent), "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data[0]["unpushed"] == {"main": 1}
    assert "branch main: 1 unpushed commit(s)" in data[0]["findings"]
