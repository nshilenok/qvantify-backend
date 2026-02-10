#!/usr/bin/env python3
"""Promote the exact staging deployment to production and update app alias."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Any


@dataclass
class PromoteConfig:
    staging_domain: str
    production_domain: str
    apply: bool


class FrontendPromoter:
    def __init__(self, config: PromoteConfig) -> None:
        self.config = config

    @staticmethod
    def parse_args() -> PromoteConfig:
        parser = argparse.ArgumentParser(
            description="Promote staging frontend deployment to production."
        )
        parser.add_argument("--staging-domain", default="staging.app.qvantify.com")
        parser.add_argument("--production-domain", default="app.qvantify.com")
        parser.add_argument("--apply", action="store_true", help="Execute promotion.")
        args = parser.parse_args()
        return PromoteConfig(
            staging_domain=args.staging_domain,
            production_domain=args.production_domain,
            apply=args.apply,
        )

    def run(self) -> int:
        self._require_command("vercel")
        staging_deploy_url = self._resolve_staging_deployment()
        if not self.config.apply:
            print("Dry-run promotion plan:")
            print(f"- Source deployment: {staging_deploy_url}")
            print("- Command: vercel redeploy <source> --target production")
            print(
                f"- Command: vercel alias set <new-production-deployment> {self.config.production_domain}"
            )
            return 0

        redeploy_output = subprocess.run(
            ["vercel", "redeploy", staging_deploy_url, "--target", "production"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        prod_url = self._parse_production_url(redeploy_output)
        if not prod_url:
            raise RuntimeError("Failed to parse production deployment URL from redeploy output.")
        subprocess.run(
            ["vercel", "alias", "set", prod_url, self.config.production_domain],
            text=True,
            check=True,
            capture_output=False,
        )
        print(f"Production alias updated: {self.config.production_domain} -> {prod_url}")
        return 0

    def _resolve_staging_deployment(self) -> str:
        output = subprocess.run(
            ["vercel", "inspect", self.config.staging_domain, "--json"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        payload = self._parse_json_blob(output)
        deployment_url = payload.get("url")
        if not deployment_url:
            raise RuntimeError("Failed to resolve staging deployment URL.")
        if not str(deployment_url).startswith("http"):
            return f"https://{deployment_url}"
        return str(deployment_url)

    @staticmethod
    def _parse_production_url(output: str) -> str:
        match = re.search(r"Production:\s*(https?://\S+)", output)
        if match:
            return match.group(1)
        fallback = re.search(r"(https?://[a-zA-Z0-9.-]+\.vercel\.app)", output)
        return fallback.group(1) if fallback else ""

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
        config = FrontendPromoter.parse_args()
        return FrontendPromoter(config).run()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
