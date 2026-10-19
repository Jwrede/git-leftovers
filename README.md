# git-leftovers

Before you hand over a project, leave a job, or wipe a laptop or VM, you need to know which work
exists only on this machine. `git status` answers that for one repository and one branch.
`git-leftovers` answers it for every repository under a directory:

- modified and untracked files
- commits that are on no remote, both on tracking branches and on local branches that were
  never pushed
- stashes
- repositories without any remote
- credential files that were added to the history at some point, even if they were deleted
  later: `.env`, `*.pem`, `id_rsa`, `*credentials*.json`, `.npmrc`, `.pgpass` and similar

It runs only local Git commands. It does not fetch, so a stale remote-tracking state shows up as
"unpushed". Run `git fetch --all` first if that matters.

## Install

```
pipx install git+https://github.com/Jwrede/git-leftovers
```

or without installing:

```
uvx --from git+https://github.com/Jwrede/git-leftovers git-leftovers ~/work
```

Python 3.10+ and `git`, no other dependencies.

## Usage

```
$ git-leftovers ~/work
/home/dev/work/billing-service  [main]  (no remote)
  - no remote: the whole repository exists only here
  - 1 modified file(s)
  - branch main: 4 unpushed commit(s)
  - secret-looking file in history: .env
/home/dev/work/data-pipeline  [main]
  - 1 untracked file(s)
  - branch fix/rounding: 1 commit(s), branch not on any remote
/home/dev/work/warehouse  [main]
  - 1 stash(es)

12 repositories, 3 with work that exists only here.
```

(Example output with illustrative paths.)

| Option | Meaning |
|---|---|
| `roots` | directories to search (default `.`); nested repositories and worktrees are found too |
| `--depth N` | maximum directory depth (default 6); `node_modules`, `.venv` and similar are skipped |
| `--all` | also list clean repositories |
| `--no-history` | skip the scan for credential files in the history (faster on very large histories) |
| `--json` | machine-readable output with a `findings` list per repository |

The exit code is 1 when any repository has leftovers and 0 when everything is pushed, so it
also works as a check in scripts.

A secret-looking file in the history is not proof of a leak. Certificates (`*.pem`) are often
public. The finding means someone should look at it before the history leaves this machine.

## License

MIT
