#!/usr/bin/env python3
"""Verify app/staging domains point to the expected Vercel frontend project."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Any


@dataclass
class AliasConfig:
    expected_project: str
    app_domain: str
    staging_domain: str
    expected_prefix: str


class AliasVerifier:
    def __init__(self, config: AliasConfig) -> None:
        self.config = config

    @staticmethod
    def parse_args() -> AliasConfig:
        parser = argparse.ArgumentParser(
            description="Verify that app/staging domains map to the expected frontend deployment."
        )
        parser.add_argument("--expected-project", default="qvantify-frontend")
        parser.add_argument("--app-domain", default="app.qvantify.com")
        parser.add_argument("--staging-domain", default="staging.app.qvantify.com")
        parser.add_argument(
            "--expected-prefix",
            default="qvantify-frontend-",
            help="Deployment URL prefix expected for app/staging aliases.",
        )
        args = parser.parse_args()
        return AliasConfig(
            expected_project=args.expected_project,
            app_domain=args.app_domain,
            staging_domain=args.staging_domain,
            expected_prefix=args.expected_prefix,
        )

    def run(self) -> int:
        self._require_command("vercel")
        app_info = self._inspect(self.config.app_domain)
        staging_info = self._inspect(self.config.staging_domain)
        self._validate_domain(app_info)
        self._validate_domain(staging_info)
        print("Alias verification passed:")
        print(
            f"- {self.config.app_domain} -> https://{app_info['url']} "
            f"(project={app_info['name']}, target={app_info.get('target')})"
        )
        print(
            f"- {self.config.staging_domain} -> https://{staging_info['url']} "
            f"(project={staging_info['name']}, target={staging_info.get('target')})"
        )
        return 0

    def _inspect(self, domain: str) -> dict[str, Any]:
        result = subprocess.run(
            ["vercel", "inspect", domain, "--json"],
            text=True,
            capture_output=True,
            check=True,
        )
        return self._parse_json_blob(result.stdout)

    def _validate_domain(self, data: dict[str, Any]) -> None:
        project_name = data.get("name", "")
        url = data.get("url", "")
        if project_name != self.config.expected_project:
            raise RuntimeError(
                f"Domain points to wrong project. expected={self.config.expected_project} got={project_name}"
            )
        if not str(url).startswith(self.config.expected_prefix):
            raise RuntimeError(
                f"Domain points to unexpected deployment URL. expected-prefix={self.config.expected_prefix} got={url}"
            )
        if data.get("readyState") != "READY":
            raise RuntimeError(f"Deployment is not READY (got={data.get('readyState')})")

    @staticmethod
    def _parse_json_blob(text: str) -> dict[str, Any]:
        start = text.find("{")
        if start < 0:
            raise RuntimeError("Could not parse JSON from vercel inspect output.")
        return json.loads(text[start:])

    @staticmethod
    def _require_command(command: str) -> None:
        if shutil.which(command):
            return
        raise RuntimeError(f"Required command not found: {command}")


def main() -> int:
    try:
        config = AliasVerifier.parse_args()
        return AliasVerifier(config).run()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
