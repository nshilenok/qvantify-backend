import os

import httpx


BASE_URL = os.environ.get("QVANTIFY_BASE_URL", "http://127.0.0.1:5055").rstrip("/")


def test_results_spa_serves():
    r = httpx.get(f"{BASE_URL}/results/", timeout=30)
    assert r.status_code == 200
    assert "Qvantify Results" in r.text
    assert "/results/assets/" in r.text


def test_results_spa_deep_link_serves():
    r = httpx.get(f"{BASE_URL}/results/admin", timeout=30)
    assert r.status_code == 200
    assert "Qvantify Results" in r.text


def test_admin_api_fails_gracefully_without_db_or_admin():
    # This endpoint should never crash the server. Depending on env, it can be:
    # - 503: DB not configured/unavailable
    # - 404: admin disabled (ADMIN_LOCAL_KEY not set)
    # - 403: not local-only (if called from non-loopback)
    r = httpx.get(f"{BASE_URL}/api/admin/projects", timeout=30)
    assert r.status_code in (200, 403, 404, 503)

