"""
E2E backend test for the Create Project flow (FacelessForge).
Validates login -> create project -> list -> fetch detail with cookie session.
"""
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

CREDS = {"email": "creator@facelessforge.io", "password": "creator123"}


@pytest.fixture(scope="module")
def authed_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=CREDS, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    body = r.json()
    assert "id" in body and body.get("email") == CREDS["email"]
    # Cookies present
    assert "access_token" in s.cookies, "access_token cookie missing"
    return s


# -- Auth ----------------------------------------------------------------
def test_login_sets_cookies_and_returns_user(authed_session):
    r = authed_session.get(f"{BASE_URL}/api/auth/me", timeout=10)
    assert r.status_code == 200
    me = r.json()
    assert me["email"] == CREDS["email"]


# -- Project create ------------------------------------------------------
PAYLOAD_TEMPLATE = {
    "niche": "design psychology",
    "topic": "Why dark mode reduces cognitive load for late-night coders",
    "audience": "designers and developers 22-40",
    "tone": "calm-authoritative",
    "target_duration": 300,
    "voice_style": "neutral male narrator",
    "visual_style": "cinematic b-roll",
    "monetisation_intent": "ads + affiliate",
    "cta_goal": "subscribe",
}


def test_create_project_persists_and_lists(authed_session):
    name = f"TEST_E2E_{uuid.uuid4().hex[:8]}_{int(time.time())}"
    payload = {**PAYLOAD_TEMPLATE, "name": name}

    # CREATE
    r = authed_session.post(f"{BASE_URL}/api/projects", json=payload, timeout=20)
    assert r.status_code == 200, f"create failed: {r.status_code} {r.text}"
    created = r.json()
    assert created["name"] == name
    assert created["niche"] == payload["niche"]
    assert created["target_duration"] == 300
    assert isinstance(created["id"], str) and len(created["id"]) > 10
    pid = created["id"]

    # GET single
    rg = authed_session.get(f"{BASE_URL}/api/projects/{pid}", timeout=10)
    assert rg.status_code == 200
    detail = rg.json()
    # endpoint returns wrapped view (project + script + scenes ...)
    project = detail.get("project", detail)
    assert project["id"] == pid
    assert project["name"] == name

    # LIST contains the new project
    rl = authed_session.get(f"{BASE_URL}/api/projects", timeout=10)
    assert rl.status_code == 200
    ids = [p["id"] for p in rl.json()]
    assert pid in ids, "new project not present in list"


def test_create_project_validation_error(authed_session):
    # Missing required fields → 422
    r = authed_session.post(f"{BASE_URL}/api/projects", json={"name": ""}, timeout=10)
    assert r.status_code in (400, 422)


def test_unauthenticated_create_blocked():
    s = requests.Session()  # no cookies
    name = f"TEST_NOAUTH_{uuid.uuid4().hex[:6]}"
    r = s.post(
        f"{BASE_URL}/api/projects",
        json={**PAYLOAD_TEMPLATE, "name": name},
        timeout=10,
    )
    assert r.status_code in (401, 403)
