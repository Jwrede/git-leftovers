from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from git_leftovers import __version__
from git_leftovers.core import find_repos, inspect


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="git-leftovers",
        description="Find Git work that exists only on this machine: uncommitted changes, unpushed commits, "
        "stashes, branches and repositories without a remote, and credential files in the history.",
    )
    ap.add_argument("roots", nargs="*", type=Path, default=[Path(".")], help="directories to search (default .)")
    ap.add_argument("--depth", type=int, default=6, help="maximum directory depth to search (default 6)")
    ap.add_argument("--all", action="store_true", help="also list clean repositories")
    ap.add_argument("--no-history", action="store_true", help="skip the scan for credential files in the history")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args(argv)

    repos = find_repos(args.roots, args.depth)
    reports = [inspect(r, check_history=not args.no_history) for r in repos]
    dirty = [r for r in reports if not r.clean]

    if args.json:
        json.dump([r.to_dict() for r in reports if args.all or not r.clean], sys.stdout, indent=2)
        print()
    else:
        for r in reports:
            if r.clean and not args.all:
                continue
            print(f"{r.path}  [{r.branch or 'no branch'}]" + ("" if r.remotes else "  (no remote)"))
            for f in r.findings or ["clean"]:
                print(f"  - {f}")
        print(f"\n{len(repos)} repositories, {len(dirty)} with work that exists only here.")
    return 1 if dirty else 0


if __name__ == "__main__":
    sys.exit(main())
