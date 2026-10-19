from __future__ import annotations

import fnmatch
import os
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

GIT_TIMEOUT = 60

# File names that usually hold credentials. Matched against the base name of every
# file ever added in the history of any branch.
SECRET_PATTERNS = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "credentials*.json",
    "*credentials*.json",
    "service-account*.json",
    "*.kdbx",
    ".netrc",
    ".pgpass",
    ".pypirc",
    ".npmrc",
)
SECRET_EXCEPTIONS = (".env.example", ".env.sample", ".env.template", ".env.dist")

SKIP_DIRS = {"node_modules", ".venv", "venv", "__pycache__", ".tox", ".mypy_cache", ".cache", "site-packages"}


class GitError(RuntimeError):
    pass


def git(repo: Path, *args: str) -> str:
    try:
        res = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"},
        )
    except subprocess.TimeoutExpired:
        raise GitError(f"git {' '.join(args)} timed out after {GIT_TIMEOUT}s") from None
    if res.returncode != 0:
        raise GitError(res.stderr.strip() or f"git {' '.join(args)} failed")
    return res.stdout


@dataclass
class RepoReport:
    path: str
    branch: str | None = None
    remotes: list[str] = field(default_factory=list)
    modified: int = 0
    untracked: int = 0
    unpushed: dict[str, int] = field(default_factory=dict)
    local_only_branches: list[str] = field(default_factory=list)
    stashes: int = 0
    secret_files: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def findings(self) -> list[str]:
        out = []
        if self.error:
            out.append(f"error: {self.error}")
        if not self.remotes:
            out.append("no remote: the whole repository exists only here")
        if self.branch is None and not self.error:
            out.append("detached HEAD")
        if self.modified:
            out.append(f"{self.modified} modified file(s)")
        if self.untracked:
            out.append(f"{self.untracked} untracked file(s)")
        for b, n in self.unpushed.items():
            if self.remotes and b in self.local_only_branches:
                out.append(f"branch {b}: {n} commit(s), branch not on any remote")
            else:
                out.append(f"branch {b}: {n} unpushed commit(s)")
        if self.stashes:
            out.append(f"{self.stashes} stash(es)")
        for f in self.secret_files:
            out.append(f"secret-looking file in history: {f}")
        return out

    @property
    def clean(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict:
        d = asdict(self)
        d["findings"] = self.findings
        return d


def find_repos(roots: list[Path], max_depth: int = 6) -> list[Path]:
    """Directories that contain a `.git` entry, including worktrees and nested repos."""
    found = []
    for root in roots:
        root = root.resolve()
        base_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            here = Path(dirpath)
            if ".git" in dirnames or ".git" in filenames:
                found.append(here)
            dirnames[:] = [
                d for d in dirnames if d != ".git" and d not in SKIP_DIRS and len(here.parts) - base_depth < max_depth
            ]
    return sorted(set(found))


def _is_secret(name: str) -> bool:
    base = os.path.basename(name)
    if base in SECRET_EXCEPTIONS:
        return False
    return any(fnmatch.fnmatch(base, pat) for pat in SECRET_PATTERNS)


def inspect(repo: Path, check_history: bool = True) -> RepoReport:
    rep = RepoReport(str(repo))
    try:
        rep.remotes = git(repo, "remote").split()
        head = git(repo, "symbolic-ref", "-q", "--short", "HEAD").strip() if _has_symbolic_head(repo) else ""
        rep.branch = head or None
        for line in git(repo, "status", "--porcelain=v1", "--untracked-files=normal").splitlines():
            if line.startswith("??"):
                rep.untracked += 1
            elif line.strip():
                rep.modified += 1
        rep.stashes = len(git(repo, "stash", "list").splitlines())
        fmt = "%(refname:short)%09%(upstream:short)%09%(upstream:track)"
        for line in git(repo, "for-each-ref", f"--format={fmt}", "refs/heads").splitlines():
            name, upstream, track = (line.split("\t") + ["", ""])[:3]
            if not upstream or "[gone]" in track:
                ahead = _commits_not_on_remotes(repo, name)
                if ahead or not rep.remotes:
                    rep.local_only_branches.append(name)
                    if ahead:
                        rep.unpushed[name] = ahead
                continue
            if "ahead" in track:
                n = int(track.split("ahead ")[1].split(",")[0].rstrip("]"))
                rep.unpushed[name] = n
        if check_history:
            added = git(repo, "log", "--all", "--diff-filter=A", "--name-only", "--format=")
            rep.secret_files = sorted({f for f in added.splitlines() if f and _is_secret(f)})
    except GitError as exc:
        rep.error = str(exc)
    return rep


def _has_symbolic_head(repo: Path) -> bool:
    try:
        git(repo, "symbolic-ref", "-q", "HEAD")
        return True
    except GitError:
        return False


def _commits_not_on_remotes(repo: Path, branch: str) -> int:
    """Commits on `branch` that no remote-tracking branch contains."""
    try:
        out = git(repo, "rev-list", "--count", branch, "--not", "--remotes")
    except GitError:
        return 0
    return int(out.strip() or 0)
