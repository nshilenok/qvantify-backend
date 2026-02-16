#!/usr/bin/env python3
"""Verify app/staging domains point to the expected Vercel frontend project."""

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
class AliasConfig:
    expected_project: str
    app_domain: str
    staging_domain: str
    expected_prefix: str
    expected_app_target: str
    expected_staging_target: str
    expected_app_proxy_base: str
    expected_staging_proxy_base: str
    probe_interview: str
    probe_external_id: str
    check_runtime: bool
    scope: str | None
    vercel_cwd: str


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
        parser.add_argument(
            "--expected-app-proxy-base",
            default="https://qvantify.up.railway.app",
            help="Expected x-qvantify-proxy-base for app domain runtime checks.",
        )
        parser.add_argument(
            "--expected-staging-proxy-base",
            default="https://qvantify-staging.up.railway.app",
            help="Expected x-qvantify-proxy-base for staging domain runtime checks.",
        )
        parser.add_argument(
            "--probe-interview",
            default="swipking2",
            help="Interview id used to verify /interview runtime route.",
        )
        parser.add_argument(
            "--probe-external-id",
            default="staging_smoke_probe",
            help="external_id used for runtime route probes.",
        )
        parser.add_argument(
            "--skip-runtime-check",
            action="store_true",
            help="Skip runtime route and proxy header checks.",
        )
        parser.add_argument(
            "--scope",
            default=None,
            help="Optional Vercel scope for inspect/curl commands.",
        )
        parser.add_argument(
            "--vercel-cwd",
            default="frontend",
            help="Directory where vercel commands should run (must be linked to qvantify-frontend).",
        )
        args = parser.parse_args()
        return AliasConfig(
            expected_project=args.expected_project,
            app_domain=args.app_domain,
            staging_domain=args.staging_domain,
            expected_prefix=args.expected_prefix,
            expected_app_target=args.expected_app_target,
            expected_staging_target=args.expected_staging_target,
            expected_app_proxy_base=args.expected_app_proxy_base,
            expected_staging_proxy_base=args.expected_staging_proxy_base,
            probe_interview=args.probe_interview,
            probe_external_id=args.probe_external_id,
            check_runtime=not args.skip_runtime_check,
            scope=args.scope,
            vercel_cwd=args.vercel_cwd,
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
        if self.config.check_runtime:
            self._validate_runtime(
                domain=self.config.app_domain,
                data=app_info,
                expected_proxy_base=self.config.expected_app_proxy_base,
            )
            self._validate_runtime(
                domain=self.config.staging_domain,
                data=staging_info,
                expected_proxy_base=self.config.expected_staging_proxy_base,
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
        cmd = ["vercel", "inspect", domain, "--json"]
        if self.config.scope:
            cmd.extend(["--scope", self.config.scope])
        result = subprocess.run(cmd, text=True, capture_output=True, check=True, cwd=self._vercel_cwd())
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

    def _validate_runtime(
        self, domain: str, data: dict[str, Any], expected_proxy_base: str
    ) -> None:
        deployment_url = str(data.get("url", "")).strip()
        if not deployment_url:
            raise RuntimeError(f"Missing deployment URL for runtime check: {domain}")
        if not deployment_url.startswith("http"):
            deployment_url = f"https://{deployment_url}"

        interview_path = (
            f"/interview?interview={self.config.probe_interview}"
            f"&external_id={self.config.probe_external_id}"
        )
        interview_status = self._curl_status(interview_path, deployment_url)
        if interview_status != 200:
            raise RuntimeError(
                "Interview route check failed. "
                f"domain={domain} deployment={deployment_url} path={interview_path} "
                f"status={interview_status}"
            )

        health_output = self._curl_include("/api/health", deployment_url)
        health_status = self._extract_http_status(health_output)
        if health_status != 200:
            raise RuntimeError(
                "Health route check failed. "
                f"domain={domain} deployment={deployment_url} status={health_status}"
            )

        proxy_match = re.search(
            r"(?im)^x-qvantify-proxy-base:\s*(\S+)\s*$", health_output
        )
        proxy_base = proxy_match.group(1).strip() if proxy_match else ""
        if expected_proxy_base and proxy_base != expected_proxy_base:
            raise RuntimeError(
                "Unexpected backend proxy base. "
                f"domain={domain} expected={expected_proxy_base} got={proxy_base or '<missing>'}"
            )
        if not re.search(r'"ok"\s*:\s*true', health_output):
            raise RuntimeError(
                f"Health payload did not contain ok=true for domain={domain}."
            )

    @staticmethod
    def _parse_json_blob(text: str) -> dict[str, Any]:
        start = text.find("{")
        if start < 0:
            raise RuntimeError("Could not parse JSON from vercel inspect output.")
        return json.loads(text[start:])

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
        cmd.extend(
            [
                "--",
                "--include",
                "--silent",
                "--show-error",
                "--location",
            ]
        )
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
