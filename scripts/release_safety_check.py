#!/usr/bin/env python3
"""Safety checks before promoting staging to production."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SafetyConfig:
    repo_path: Path
    allow_dirty: bool
    allow_divergence: bool
    skip_alias_check: bool


class ReleaseSafetyChecker:
    def __init__(self, config: SafetyConfig) -> None:
        self.config = config

    @staticmethod
    def parse_args() -> SafetyConfig:
        parser = argparse.ArgumentParser(
            description="Fail fast if release preconditions are not met."
        )
        parser.add_argument("--repo-path", default=".")
        parser.add_argument("--allow-dirty", action="store_true")
        parser.add_argument("--allow-divergence", action="store_true")
        parser.add_argument("--skip-alias-check", action="store_true")
        args = parser.parse_args()
        return SafetyConfig(
            repo_path=Path(args.repo_path).resolve(),
            allow_dirty=args.allow_dirty,
            allow_divergence=args.allow_divergence,
            skip_alias_check=args.skip_alias_check,
        )

    def run(self) -> int:
        self._require_command("git")
        if not self.config.skip_alias_check:
            self._require_command("vercel")
        if not self.config.repo_path.exists():
            raise RuntimeError(f"Repo path does not exist: {self.config.repo_path}")
        self._check_dirty_tree()
        self._check_branch_divergence()
        if not self.config.skip_alias_check:
            self._check_domain_aliases()
        print("Release safety check passed.")
        return 0

    def _check_dirty_tree(self) -> None:
        result = self._git("status", "--porcelain")
        dirty_lines = [line for line in result.splitlines() if line.strip()]
        if dirty_lines and not self.config.allow_dirty:
            preview = "\n".join(dirty_lines[:20])
            raise RuntimeError(
                "Working tree is dirty. Commit/stash changes before release.\n" + preview
            )

    def _check_branch_divergence(self) -> None:
        self._git("fetch", "origin")
        result = self._git("rev-list", "--left-right", "--count", "origin/main...origin/staging")
        left, right = [int(part) for part in result.split()]
        payload = {"main_ahead": left, "staging_ahead": right}
        print(f"Branch divergence: {json.dumps(payload)}")
        if left > 0 and right > 0 and not self.config.allow_divergence:
            raise RuntimeError(
                "Both branches diverged. Resolve branch parity before promotion."
            )

    def _check_domain_aliases(self) -> None:
        script = self.config.repo_path / "scripts" / "verify_domain_aliases.py"
        if not script.exists():
            raise RuntimeError(f"Missing alias verifier: {script}")
        result = subprocess.run(
            ["python3", str(script)],
            cwd=self.config.repo_path,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "Domain alias check failed.\n"
                + (result.stdout or "")
                + (result.stderr or "")
            )
        print(result.stdout.strip())

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.config.repo_path,
            text=True,
            capture_output=True,
            check=True,
        )
        return result.stdout.strip()

    @staticmethod
    def _require_command(command: str) -> None:
        if shutil.which(command):
            return
        raise RuntimeError(f"Required command not found: {command}")


def main() -> int:
    try:
        config = ReleaseSafetyChecker.parse_args()
        return ReleaseSafetyChecker(config).run()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
