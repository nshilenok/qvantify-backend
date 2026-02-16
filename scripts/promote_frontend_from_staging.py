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
from pathlib import Path
from typing import Any


@dataclass
class PromoteConfig:
    staging_domain: str
    production_domain: str
    apply: bool
    scope: str | None
    vercel_cwd: str
    expected_staging_proxy_base: str
    probe_interview: str
    probe_external_id: str
    skip_runtime_check: bool


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
        parser.add_argument(
            "--scope",
            default=None,
            help="Optional Vercel scope for inspect/redeploy/alias commands.",
        )
        parser.add_argument(
            "--vercel-cwd",
            default="frontend",
            help="Directory where Vercel project is linked (default: frontend).",
        )
        parser.add_argument(
            "--expected-staging-proxy-base",
            default="https://qvantify-staging.up.railway.app",
            help="Expected x-qvantify-proxy-base value for source staging deployment.",
        )
        parser.add_argument(
            "--probe-interview",
            default="swipking2",
            help="Interview id used to verify source staging runtime before promotion.",
        )
        parser.add_argument(
            "--probe-external-id",
            default="promotion_source_probe",
            help="external_id used in source runtime probe.",
        )
        parser.add_argument(
            "--skip-runtime-check",
            action="store_true",
            help="Skip source runtime validation before promotion.",
        )
        args = parser.parse_args()
        return PromoteConfig(
            staging_domain=args.staging_domain,
            production_domain=args.production_domain,
            apply=args.apply,
            scope=args.scope,
            vercel_cwd=args.vercel_cwd,
            expected_staging_proxy_base=args.expected_staging_proxy_base,
            probe_interview=args.probe_interview,
            probe_external_id=args.probe_external_id,
            skip_runtime_check=args.skip_runtime_check,
        )

    def run(self) -> int:
        self._require_command("vercel")
        staging_deploy_url = self._resolve_staging_deployment()
        if not self.config.skip_runtime_check:
            self._validate_source_runtime(staging_deploy_url)
        if not self.config.apply:
            print("Dry-run promotion plan:")
            print(f"- Source deployment: {staging_deploy_url}")
            print("- Command: vercel redeploy <source> --target production")
            print(
                f"- Command: vercel alias set <new-production-deployment> {self.config.production_domain}"
            )
            return 0

        redeploy_cmd = ["vercel", "redeploy", staging_deploy_url, "--target", "production"]
        if self.config.scope:
            redeploy_cmd.extend(["--scope", self.config.scope])
        redeploy_output = subprocess.run(
            redeploy_cmd,
            text=True,
            capture_output=True,
            check=True,
            cwd=self._vercel_cwd(),
        ).stdout
        prod_url = self._parse_production_url(redeploy_output)
        if not prod_url:
            raise RuntimeError("Failed to parse production deployment URL from redeploy output.")
        alias_cmd = ["vercel", "alias", "set", prod_url, self.config.production_domain]
        if self.config.scope:
            alias_cmd.extend(["--scope", self.config.scope])
        subprocess.run(
            alias_cmd,
            text=True,
            check=True,
            capture_output=False,
            cwd=self._vercel_cwd(),
        )
        print(f"Production alias updated: {self.config.production_domain} -> {prod_url}")
        return 0

    def _resolve_staging_deployment(self) -> str:
        inspect_cmd = ["vercel", "inspect", self.config.staging_domain, "--json"]
        if self.config.scope:
            inspect_cmd.extend(["--scope", self.config.scope])
        output = subprocess.run(
            inspect_cmd,
            text=True,
            capture_output=True,
            check=True,
            cwd=self._vercel_cwd(),
        ).stdout
        payload = self._parse_json_blob(output)
        deployment_url = payload.get("url")
        if not deployment_url:
            raise RuntimeError("Failed to resolve staging deployment URL.")
        if not str(deployment_url).startswith("http"):
            return f"https://{deployment_url}"
        return str(deployment_url)

    def _validate_source_runtime(self, deployment_url: str) -> None:
        interview_path = (
            f"/interview?interview={self.config.probe_interview}"
            f"&external_id={self.config.probe_external_id}"
        )
        interview_status = self._curl_status(interview_path, deployment_url)
        if interview_status != 200:
            raise RuntimeError(
                "Source staging deployment failed runtime validation: "
                f"path={interview_path} status={interview_status} deployment={deployment_url}"
            )

        health_output = self._curl_include("/api/health", deployment_url)
        health_status = self._extract_http_status(health_output)
        if health_status != 200:
            raise RuntimeError(
                "Source staging deployment failed health check: "
                f"status={health_status} deployment={deployment_url}"
            )

        proxy_match = re.search(
            r"(?im)^x-qvantify-proxy-base:\s*(\S+)\s*$", health_output
        )
        proxy_base = proxy_match.group(1).strip() if proxy_match else ""
        expected = self.config.expected_staging_proxy_base
        if expected and proxy_base != expected:
            raise RuntimeError(
                "Source staging deployment has unexpected backend target: "
                f"expected={expected} got={proxy_base or '<missing>'} deployment={deployment_url}"
            )

    def _curl_status(self, path: str, deployment_url: str) -> int:
        cmd = ["vercel", "curl", path, "--deployment", deployment_url]
        if self.config.scope:
            cmd.extend(["--scope", self.config.scope])
        cmd.extend(
            [
                "--",
                "--silent",
                "--show-error",
                "--location",
                "--output",
                "/dev/null",
                "--write-out",
                "STATUS:%{http_code}",
            ]
        )
        result = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            check=True,
            cwd=self._vercel_cwd(),
        )
        match = re.search(r"STATUS:(\d{3})", result.stdout)
        if not match:
            raise RuntimeError(
                "Could not parse HTTP status from vercel curl output.\n"
                + (result.stdout or "")
                + (result.stderr or "")
            )
        return int(match.group(1))

    def _curl_include(self, path: str, deployment_url: str) -> str:
        cmd = ["vercel", "curl", path, "--deployment", deployment_url]
        if self.config.scope:
            cmd.extend(["--scope", self.config.scope])
        cmd.extend(["--", "--include", "--silent", "--show-error", "--location"])
        result = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            check=True,
            cwd=self._vercel_cwd(),
        )
        return result.stdout

    @staticmethod
    def _extract_http_status(text: str) -> int:
        match = re.search(r"(?im)^HTTP/\S+\s+(\d{3})", text)
        return int(match.group(1)) if match else 0

    def _vercel_cwd(self) -> str:
        cwd = Path(self.config.vercel_cwd)
        if not cwd.is_absolute():
            cwd = Path.cwd() / cwd
        if not cwd.exists():
            raise RuntimeError(f"vercel cwd does not exist: {cwd}")
        return str(cwd)

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
