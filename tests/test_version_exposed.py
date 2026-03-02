"""APP_VERSION is resolved at startup and exposed via /api/health and response payloads."""

from pathlib import Path
import sys

import pytest
from flask import Flask, g

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import server as srv


def test_app_version_is_non_empty_string():
    assert isinstance(srv.APP_VERSION, str)
    assert len(srv.APP_VERSION) > 0


def test_app_version_is_not_placeholder():
    assert srv.APP_VERSION != "", "APP_VERSION must not be empty"


def test_health_endpoint_includes_version():
    with srv.app.test_request_context("/api/health", method="GET"):
        response = srv.health()
        if isinstance(response, tuple):
            data = response[0].get_json()
        else:
            data = response.get_json()
        assert "version" in data, "/api/health must include 'version' field"
        assert isinstance(data["version"], str)
        assert len(data["version"]) > 0


def test_resolve_app_version_from_env(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abc1234567890")
    result = srv._resolve_app_version()
    assert result == "abc1234", "Should use first 7 chars of RAILWAY_GIT_COMMIT_SHA"


def test_resolve_app_version_fallback_without_env(monkeypatch):
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    result = srv._resolve_app_version()
    assert isinstance(result, str)
    assert len(result) > 0, "Should fall back to git SHA or 'dev'"


def test_frontend_nextconfig_injects_build_sha():
    config_path = ROOT_DIR / "frontend" / "next.config.ts"
    source = config_path.read_text(encoding="utf-8")
    assert "NEXT_PUBLIC_BUILD_SHA" in source, "next.config.ts must inject NEXT_PUBLIC_BUILD_SHA"
    assert "VERCEL_GIT_COMMIT_SHA" in source, "next.config.ts must read VERCEL_GIT_COMMIT_SHA"


def test_frontend_logs_version_on_mount():
    client_path = ROOT_DIR / "frontend" / "app" / "interview" / "InterviewClient.tsx"
    source = client_path.read_text(encoding="utf-8")
    assert "FE_VERSION" in source, "InterviewClient must reference FE_VERSION"
    assert "logBeVersion" in source, "InterviewClient must call logBeVersion"
    assert "[qvantify]" in source, "Version log must use [qvantify] prefix"
