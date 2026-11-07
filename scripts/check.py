#!/usr/bin/env python3
"""Single check command: runs the test suite wherever that is possible.

Modes, chosen by environment:

* Linux/macOS: ``python -m pytest`` locally.
* Windows with WSL and a test venv inside WSL: pytest through ``wsl``.
  The venv is ``$MIOT_WSL_VENV`` (a Linux path) or ``.venv-wsl`` in the repo.
* Windows without a Linux environment: CI mode. Pushes the current branch
  and waits for the GitHub Actions run of this commit.

Extra arguments are passed to pytest (local and WSL mode only).
The exit code is the test result. Standard library only.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = "tests.yml"
WSL_VENV_ENV = "MIOT_WSL_VENV"
WSL_VENV_DIR = ".venv-wsl"
RUN_WAIT_SECONDS = 90
RUN_POLL_SECONDS = 5


def say(text: str) -> None:
    print(f"[check] {text}", flush=True)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, **kwargs)


def output(cmd: list[str], timeout: float = 60) -> tuple[int, str]:
    """Runs a command, returns (exit code, stdout as text)."""
    try:
        proc = run(cmd, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    return proc.returncode, proc.stdout.decode("utf-8", errors="replace").strip()


# --- Local (Linux/macOS) ---------------------------------------------------


def local_mode(pytest_args: list[str]) -> int:
    say(f"mode: local ({sys.platform}), running pytest with {sys.executable}")
    if importlib.util.find_spec("pytest_homeassistant_custom_component") is None:
        say("pytest-homeassistant-custom-component is not installed. Set up with:")
        say("  python3.14 -m venv .venv && . .venv/bin/activate")
        say("  pip install -r requirements_test.txt")
        return 2
    return run([sys.executable, "-m", "pytest", *pytest_args]).returncode


# --- WSL --------------------------------------------------------------------


def find_wsl_venv() -> tuple[str | None, str]:
    """Returns (Linux path of the venv, reason) or (None, reason)."""
    if shutil.which("wsl") is None:
        return None, "wsl.exe not found"
    code, _ = output(["wsl", "-e", "true"])
    if code != 0:
        return None, "WSL is not installed or has no distribution"
    candidates: list[str] = []
    if env := os.environ.get(WSL_VENV_ENV):
        candidates.append(env.rstrip("/"))
    code, repo = output(["wsl", "-e", "wslpath", "-a", str(ROOT)])
    if code == 0 and repo:
        candidates.append(f"{repo}/{WSL_VENV_DIR}")
    for venv in candidates:
        code, _ = output(["wsl", "-e", "test", "-x", f"{venv}/bin/python"])
        if code == 0:
            return venv, f"WSL venv found at {venv}"
    return None, (
        f"WSL is installed, but no venv was found ({WSL_VENV_ENV} or "
        f"{WSL_VENV_DIR}/ in the repo; see README, Development)"
    )


def wsl_mode(venv: str, reason: str, pytest_args: list[str]) -> int:
    say(f"mode: WSL ({reason})")
    cmd = ["wsl", "--cd", str(ROOT), "-e", f"{venv}/bin/python", "-m", "pytest"]
    return run([*cmd, *pytest_args]).returncode


# --- CI (Windows without Linux) ---------------------------------------------


def default_branch() -> str | None:
    code, name = output(
        ["gh", "repo", "view", "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name"]
    )
    return name if code == 0 and name else None


def find_run(sha: str) -> str | None:
    """Waits until the workflow run for the commit shows up."""
    deadline = time.monotonic() + RUN_WAIT_SECONDS
    while True:
        code, run_id = output(
            [
                "gh", "run", "list",
                "--commit", sha,
                "--workflow", WORKFLOW,
                "--event", "push",
                "--limit", "1",
                "--json", "databaseId",
                "-q", ".[0].databaseId",
            ]
        )
        if code == 0 and run_id:
            return run_id
        if time.monotonic() >= deadline:
            return None
        time.sleep(RUN_POLL_SECONDS)


def ci_mode(reason: str, pytest_args: list[str]) -> int:
    say(f"mode: CI ({reason}); tests run in GitHub Actions")
    if pytest_args:
        say(f"note: pytest arguments are ignored in CI mode: {' '.join(pytest_args)}")
    if shutil.which("gh") is None:
        say("GitHub CLI (gh) is missing. Install it and run 'gh auth login'.")
        return 2

    code, branch = output(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if code != 0 or not branch or branch == "HEAD":
        say("no branch checked out (detached HEAD). Switch to a feature branch.")
        return 2
    protected = {"main", "master"}
    if (default := default_branch()) is not None:
        protected.add(default)
    if branch in protected:
        say(f"refusing to push '{branch}'. Switch to a feature branch.")
        return 2

    code, dirty = output(["git", "status", "--porcelain"])
    if code != 0:
        say("git status failed.")
        return 2
    if dirty:
        say("the working tree has uncommitted changes. CI only tests commits.")
        say("Commit (or stash) them first:")
        for line in dirty.splitlines()[:20]:
            say(f"  {line}")
        return 2

    code, sha = output(["git", "rev-parse", "HEAD"])
    if code != 0 or not sha:
        say("git rev-parse HEAD failed.")
        return 2

    say(f"pushing '{branch}' ({sha[:8]}) to origin")
    if run(["git", "push", "-u", "origin", "HEAD"]).returncode != 0:
        say("git push failed.")
        return 2

    say(f"waiting for the '{WORKFLOW}' run of {sha[:8]}")
    run_id = find_run(sha)
    if run_id is None:
        say(f"no run found after {RUN_WAIT_SECONDS} s. Check: gh run list --commit {sha}")
        return 2

    result = run(["gh", "run", "watch", run_id, "--exit-status"]).returncode
    if result != 0:
        say("tests failed. Failed steps:")
        run(["gh", "run", "view", run_id, "--log-failed"])
    else:
        say("tests passed.")
    return result


def main(argv: list[str]) -> int:
    pytest_args = argv[1:]
    if sys.platform != "win32":
        return local_mode(pytest_args)
    venv, reason = find_wsl_venv()
    if venv is not None:
        return wsl_mode(venv, reason, pytest_args)
    return ci_mode(reason, pytest_args)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
