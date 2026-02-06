from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List, Tuple


def run_git(args: List[str], cwd: Path | None = None, timeout_s: int = 120) -> Tuple[int, str, str]:
    env = dict(os.environ)
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env.setdefault("GIT_ASKPASS", "echo")
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
        env=env,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def is_git_available() -> bool:
    rc, _, _ = run_git(["--version"], cwd=None, timeout_s=10)
    return rc == 0


def clone(repo_url: str, branch: str, mirror_dir: Path) -> None:
    mirror_dir.parent.mkdir(parents=True, exist_ok=True)
    rc, out, err = run_git(["clone", "--branch", branch, repo_url, str(mirror_dir)], cwd=None)
    if rc != 0:
        raise RuntimeError(err or out or "git clone failed")


def fetch(mirror_dir: Path) -> None:
    rc, out, err = run_git(["-C", str(mirror_dir), "fetch", "--prune"], cwd=None)
    if rc != 0:
        raise RuntimeError(err or out or "git fetch failed")


def checkout_branch(mirror_dir: Path, branch: str) -> None:
    rc, out, err = run_git(["-C", str(mirror_dir), "checkout", branch], cwd=None)
    if rc != 0:
        raise RuntimeError(err or out or "git checkout failed")


def hard_reset_to_origin(mirror_dir: Path, branch: str) -> None:
    rc, out, err = run_git(["-C", str(mirror_dir), "reset", "--hard", f"origin/{branch}"], cwd=None)
    if rc != 0:
        raise RuntimeError(err or out or "git reset failed")
    rc, out, err = run_git(["-C", str(mirror_dir), "clean", "-fd"], cwd=None)
    if rc != 0:
        raise RuntimeError(err or out or "git clean failed")


def head_commit(mirror_dir: Path, ref: str = "HEAD") -> str:
    rc, out, err = run_git(["-C", str(mirror_dir), "rev-parse", ref], cwd=None)
    if rc != 0:
        raise RuntimeError(err or out or "git rev-parse failed")
    return out.strip()


def diff_name_status(mirror_dir: Path, old: str, new: str) -> list[tuple[str, str]]:
    rc, out, err = run_git(["-C", str(mirror_dir), "diff", "--name-status", f"{old}..{new}"], cwd=None)
    if rc != 0:
        raise RuntimeError(err or out or "git diff failed")
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            rows.append((parts[0].strip(), parts[1].strip()))
    return rows
