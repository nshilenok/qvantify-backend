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
    expected_app_target: str
    expected_staging_target: str


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
        parser.add_argument(
            "--expected-app-target",
            default="production",
            help="Expected Vercel target for app domain.",
        )
        parser.add_argument(
            "--expected-staging-target",
            default="preview",
            help="Expected Vercel target for staging domain.",
        )
        args = parser.parse_args()
        return AliasConfig(
            expected_project=args.expected_project,
            app_domain=args.app_domain,
            staging_domain=args.staging_domain,
            expected_prefix=args.expected_prefix,
            expected_app_target=args.expected_app_target,
            expected_staging_target=args.expected_staging_target,
        )

    def run(self) -> int:
        self._require_command("vercel")
        app_info = self._inspect(self.config.app_domain)
        staging_info = self._inspect(self.config.staging_domain)
        self._validate_domain(
            domain=self.config.app_domain,
            data=app_info,
            expected_target=self.config.expected_app_target,
        )
        self._validate_domain(
            domain=self.config.staging_domain,
            data=staging_info,
            expected_target=self.config.expected_staging_target,
        )
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

    def _validate_domain(
        self, domain: str, data: dict[str, Any], expected_target: str
    ) -> None:
        project_name = data.get("name", "")
        url = data.get("url", "")
        target = str(data.get("target", ""))
        if project_name != self.config.expected_project:
            raise RuntimeError(
                "Domain points to wrong project. "
                f"domain={domain} expected={self.config.expected_project} got={project_name}. "
                "Policy: app/staging domains are exclusive to qvantify-frontend."
            )
        if not str(url).startswith(self.config.expected_prefix):
            raise RuntimeError(
                "Domain points to unexpected deployment URL. "
                f"domain={domain} expected-prefix={self.config.expected_prefix} got={url}. "
                "Policy: only stable app/staging domains are allowed."
            )
        if target != expected_target:
            raise RuntimeError(
                "Domain has wrong target environment. "
                f"domain={domain} expected-target={expected_target} got={target}. "
                "Set app.qvantify.com -> production and staging.app.qvantify.com -> preview."
            )
        if data.get("readyState") != "READY":
            raise RuntimeError(
                f"Deployment is not READY for domain={domain} (got={data.get('readyState')})"
            )

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
