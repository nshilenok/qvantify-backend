import json
import os
import uuid

import httpx
import pytest


BASE_URL = os.environ.get("QVANTIFY_BASE_URL", "http://127.0.0.1:5055").rstrip("/")
PROJECT_ID = os.environ.get("QVANTIFY_PROJECT_ID", "sample_game_funnel_2026_01_14")
EXTERNAL_ID = os.environ.get("QVANTIFY_EXTERNAL_ID", "sample@user.com")


def _headers(**extra):
    h = {"Accept": "application/json", "Content-Type": "application/json", "projectId": PROJECT_ID}
    h.update(extra)
    return h


def _skip_if_db_not_configured():
    try:
        r = httpx.get(f"{BASE_URL}/api/health", timeout=10)
        if r.status_code != 200:
            pytest.skip("Server health unavailable")
        data = r.json()
        if not data.get("db_configured"):
            pytest.skip("DB not configured (set DATABASE_URL or DB_* env vars)")
    except Exception:
        pytest.skip("Server health unavailable")


def test_project_config_loads():
    _skip_if_db_not_configured()
    r = httpx.get(f"{BASE_URL}/api/project/", headers=_headers(), timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) == 1
    assert "success_message" in data[0]
    assert "abort_title" in data[0]
    assert "abort_message" in data[0]


def test_create_respondent_and_initialize_interview():
    _skip_if_db_not_configured()
    r = httpx.post(
        f"{BASE_URL}/api/respondent/",
        headers=_headers(externalId=EXTERNAL_ID),
        json={"email": "no@email.com", "consent": True},
        timeout=30,
    )
    assert r.status_code == 200
    out = r.json()
    user_id = out["uuid"]
    assert out["projectId"] == PROJECT_ID
    uuid.UUID(str(user_id))  # validates format

    r2 = httpx.get(f"{BASE_URL}/api/interview/", headers=_headers(uuid=str(user_id)), timeout=30)
    assert r2.status_code == 200
    body = r2.json()
    assert body["status"] in ("open", "closed")
    assert isinstance(body.get("response"), str)


def test_reply_streaming_sse_final_event():
    _skip_if_db_not_configured()
    # Create a fresh respondent to isolate this test
    r = httpx.post(
        f"{BASE_URL}/api/respondent/",
        headers=_headers(externalId=EXTERNAL_ID),
        json={"email": "no@email.com", "consent": True},
        timeout=30,
    )
    user_id = r.json()["uuid"]

    # Initialize to ensure topics_log exists
    _ = httpx.get(f"{BASE_URL}/api/interview/", headers=_headers(uuid=str(user_id)), timeout=30)

    final = None
    deltas = 0

    with httpx.Client(timeout=60) as client:
        with client.stream(
            "POST",
            f"{BASE_URL}/api/reply/",
            headers=_headers(uuid=str(user_id), Accept="text/event-stream"),
            json={"message": "ok", "stream": True},
        ) as resp:
            assert resp.status_code == 200
            buf = ""
            for chunk in resp.iter_text():
                buf += chunk
                while "\n\n" in buf:
                    event, buf = buf.split("\n\n", 1)
                    for line in event.split("\n"):
                        if line.startswith("data: "):
                            payload = json.loads(line[6:])
                            if payload.get("type") == "delta":
                                deltas += 1
                            if payload.get("type") == "final":
                                final = payload
            assert final is not None
            assert "response" in final
            assert final.get("status") in ("open", "closed")

