#!/usr/bin/env python3
"""Create a CI/CD rollback checkpoint for qvantify domains and branches."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class CheckpointConfig:
    repo_path: Path
    checkpoint_name: str
    output_dir: Path
    force_tags: bool


class CheckpointCreator:
    def __init__(self, config: CheckpointConfig) -> None:
        self.config = config

    @staticmethod
    def parse_args() -> CheckpointConfig:
        parser = argparse.ArgumentParser(
            description="Create rollback checkpoint tags and deployment snapshot."
        )
        parser.add_argument(
            "--repo-path",
            default=".",
            help="Path to qvantify repository root.",
        )
        parser.add_argument(
            "--name",
            default=datetime.now(UTC).strftime("%Y%m%d-%H%M%S"),
            help="Checkpoint suffix, e.g. 20260210-153000.",
        )
        parser.add_argument(
            "--output-dir",
            default="ops/checkpoints",
            help="Directory where snapshot JSON is written.",
        )
        parser.add_argument(
            "--force-tags",
            action="store_true",
            help="Replace checkpoint tags if they already exist.",
        )
        args = parser.parse_args()

        repo_path = Path(args.repo_path).resolve()
        output_dir = Path(args.output_dir)
        if not output_dir.is_absolute():
            output_dir = repo_path / output_dir

        return CheckpointConfig(
            repo_path=repo_path,
            checkpoint_name=args.name,
            output_dir=output_dir,
            force_tags=args.force_tags,
        )

    def run(self) -> int:
        if not self.config.repo_path.exists():
            raise RuntimeError(f"Repository path does not exist: {self.config.repo_path}")
        self._require_command("git")
        self._require_command("vercel")

        main_sha = self._git("rev-parse", "main")
        staging_sha = self._git("rev-parse", "staging")
        origin_main_sha = self._git("rev-parse", "origin/main")
        origin_staging_sha = self._git("rev-parse", "origin/staging")
        current_branch = self._git("rev-parse", "--abbrev-ref", "HEAD")

        main_tag = f"checkpoint/main-{self.config.checkpoint_name}"
        staging_tag = f"checkpoint/staging-{self.config.checkpoint_name}"
        self._create_annotated_tag(main_tag, main_sha)
        self._create_annotated_tag(staging_tag, staging_sha)

        app_info = self._inspect_domain("app.qvantify.com")
        staging_info = self._inspect_domain("staging.app.qvantify.com")

        snapshot = {
            "created_at_utc": datetime.now(UTC).isoformat(),
            "checkpoint_name": self.config.checkpoint_name,
            "repository": str(self.config.repo_path),
            "git": {
                "current_branch": current_branch,
                "local_main_sha": main_sha,
                "local_staging_sha": staging_sha,
                "origin_main_sha": origin_main_sha,
                "origin_staging_sha": origin_staging_sha,
            },
            "restore_tags": {
                "main_tag": main_tag,
                "staging_tag": staging_tag,
            },
            "vercel": {
                "app_domain": app_info,
                "staging_domain": staging_info,
            },
        }

        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.config.output_dir / f"checkpoint-{self.config.checkpoint_name}.json"
        output_path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")

        rollback_script = self.config.repo_path / "scripts" / "rollback_domains.py"
        dry_run_cmd = f"python3 {rollback_script} --snapshot {output_path}"
        apply_cmd = f"python3 {rollback_script} --snapshot {output_path} --apply"
        print("Checkpoint created successfully:")
        print(f"- Main tag: {main_tag}")
        print(f"- Staging tag: {staging_tag}")
        print(f"- Snapshot: {output_path}")
        print("- Rollback commands:")
        print(f"  Dry-run: {dry_run_cmd}")
        print(f"  Apply:   {apply_cmd}")
        return 0

    def _run(
        self,
        command: list[str],
        *,
        capture_output: bool = True,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=self.config.repo_path,
            text=True,
            capture_output=capture_output,
            check=check,
        )

    def _git(self, *args: str) -> str:
        result = self._run(["git", *args])
        return result.stdout.strip()

    def _create_annotated_tag(self, tag_name: str, target_sha: str) -> None:
        existing = self._run(["git", "tag", "-l", tag_name]).stdout.strip()
        if existing:
            if not self.config.force_tags:
                raise RuntimeError(
                    f"Tag already exists: {tag_name}. Use --force-tags to replace it."
                )
            self._run(["git", "tag", "-d", tag_name], capture_output=False)

        message = f"Rollback checkpoint {tag_name}"
        self._run(
            ["git", "tag", "-a", tag_name, target_sha, "-m", message],
            capture_output=False,
        )

    def _inspect_domain(self, domain: str) -> dict[str, Any]:
        output = self._run(["vercel", "inspect", domain, "--json"]).stdout
        data = self._parse_json_blob(output)
        deployment_url = data.get("url", "")
        if deployment_url and not str(deployment_url).startswith("http"):
            deployment_url = f"https://{deployment_url}"
        return {
            "domain": domain,
            "deployment_id": data.get("id", ""),
            "deployment_url": deployment_url,
            "project_name": data.get("name", ""),
            "target": data.get("target", ""),
            "ready_state": data.get("readyState", ""),
            "created_at": data.get("createdAt", ""),
        }

    @staticmethod
    def _parse_json_blob(text: str) -> dict[str, Any]:
        start = text.find("{")
        if start < 0:
            raise RuntimeError("Failed to parse JSON output from CLI.")
        return json.loads(text[start:])

    @staticmethod
    def _require_command(command: str) -> None:
        if shutil.which(command):
            return
        raise RuntimeError(f"Required command not found: {command}")


def main() -> int:
    try:
        config = CheckpointCreator.parse_args()
        return CheckpointCreator(config).run()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
