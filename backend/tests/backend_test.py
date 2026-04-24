"""
FacelessForge Backend API tests.
Covers: health, auth (login/register/logout/me + invalid), projects CRUD,
generation flows (script/scenes/metadata/thumbnails/render), exports,
analytics, settings, admin RBAC, ownership & role-based access.
"""
import os
import io
import uuid
import time
import zipfile
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN_EMAIL = "admin@facelessforge.io"
ADMIN_PASSWORD = "admin123"
CREATOR_EMAIL = "creator@facelessforge.io"
CREATOR_PASSWORD = "creator123"


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def creator_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": CREATOR_EMAIL, "password": CREATOR_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"creator login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


# ---------- Health ----------
def test_health():
    r = requests.get(f"{BASE_URL}/api/health", timeout=15)
    assert r.status_code == 200
    assert r.json() == {"ok": True, "service": "facelessforge"}


# ---------- Auth ----------
class TestAuth:
    def test_login_creator_sets_cookies(self):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login", json={"email": CREATOR_EMAIL, "password": CREATOR_PASSWORD}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == CREATOR_EMAIL
        assert data["role"] == "creator"
        assert "password_hash" not in data or data.get("password_hash") is None
        # httpOnly cookies
        cookie_headers = r.headers.get_all("set-cookie") if hasattr(r.headers, "get_all") else r.raw.headers.getlist("set-cookie")
        joined = "\n".join(cookie_headers).lower()
        assert "access_token" in joined and "httponly" in joined
        assert "refresh_token" in joined

    def test_login_admin(self):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

    def test_me_with_cookie(self, creator_session):
        r = creator_session.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 200
        assert r.json()["email"] == CREATOR_EMAIL

    def test_invalid_credentials(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": CREATOR_EMAIL, "password": "wrong"}, timeout=15)
        assert r.status_code == 401

    def test_register_and_logout(self):
        s = requests.Session()
        email = f"test_reg_{uuid.uuid4().hex[:8]}@example.com"
        r = s.post(f"{BASE_URL}/api/auth/register", json={
            "name": "TEST User", "email": email, "password": "pw123456", "role": "creator"
        }, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["email"] == email
        assert j["role"] == "creator"
        # me works
        me = s.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert me.status_code == 200
        # logout
        lo = s.post(f"{BASE_URL}/api/auth/logout", timeout=15)
        assert lo.status_code == 200
        # clear session cookies for a fresh check (cookies are overwritten but may not be deleted in requests)
        s2 = requests.Session()
        r2 = s2.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r2.status_code == 401


# ---------- Projects ----------
class TestProjects:
    def test_list_seeded(self, creator_session):
        r = creator_session.get(f"{BASE_URL}/api/projects", timeout=20)
        assert r.status_code == 200
        projects = r.json()
        assert isinstance(projects, list)
        assert len(projects) >= 3, f"expected >=3 seeded projects, got {len(projects)}"

    def test_create_valid(self, creator_session):
        payload = {
            "name": "TEST_project_create",
            "niche": "finance",
            "topic": "How compounding interest accelerates wealth building",
            "audience": "beginners",
            "tone": "calm-authoritative",
            "target_duration": 300,
        }
        r = creator_session.post(f"{BASE_URL}/api/projects", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["status"] == "DRAFT"
        assert p["name"] == "TEST_project_create"
        # fetch back
        g = creator_session.get(f"{BASE_URL}/api/projects/{p['id']}", timeout=15)
        assert g.status_code == 200
        assert g.json()["project"]["id"] == p["id"]
        # cleanup
        creator_session.delete(f"{BASE_URL}/api/projects/{p['id']}", timeout=15)

    def test_create_invalid_niche(self, creator_session):
        bad = {"name": "x", "niche": "ab", "topic": "Valid topic that is long enough",
               "audience": "x", "tone": "y", "target_duration": 120}
        r = creator_session.post(f"{BASE_URL}/api/projects", json=bad, timeout=15)
        assert r.status_code == 422

    def test_create_invalid_duration(self, creator_session):
        bad = {"name": "x", "niche": "abc", "topic": "Valid topic text here",
               "audience": "x", "tone": "y", "target_duration": 10}
        r = creator_session.post(f"{BASE_URL}/api/projects", json=bad, timeout=15)
        assert r.status_code == 422

    def test_patch_and_delete(self, creator_session):
        payload = {"name": "TEST_upd", "niche": "tech", "topic": "Valid topic long enough description",
                   "audience": "devs", "tone": "neutral", "target_duration": 120}
        p = creator_session.post(f"{BASE_URL}/api/projects", json=payload, timeout=15).json()
        r = creator_session.patch(f"{BASE_URL}/api/projects/{p['id']}", json={"name": "TEST_upd_renamed"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["project"]["name"] == "TEST_upd_renamed"
        d = creator_session.delete(f"{BASE_URL}/api/projects/{p['id']}", timeout=15)
        assert d.status_code == 200
        # verify gone
        g = creator_session.get(f"{BASE_URL}/api/projects/{p['id']}", timeout=15)
        assert g.status_code == 404


# ---------- Generation (uses one shared project) ----------
@pytest.fixture(scope="module")
def gen_project(creator_session):
    payload = {
        "name": "TEST_gen_pipeline",
        "niche": "science",
        "topic": "How black holes distort spacetime around them",
        "audience": "curious learners",
        "tone": "calm-authoritative",
        "target_duration": 180,
    }
    p = creator_session.post(f"{BASE_URL}/api/projects", json=payload, timeout=20).json()
    yield p
    creator_session.delete(f"{BASE_URL}/api/projects/{p['id']}", timeout=15)


class TestGeneration:
    def test_generate_script(self, creator_session, gen_project):
        r = creator_session.post(f"{BASE_URL}/api/projects/{gen_project['id']}/generate-script", timeout=180)
        assert r.status_code == 200, r.text
        view = r.json()
        assert view["script"] is not None
        s = view["script"]
        for k in ("hook_option_one", "hook_option_two", "hook_option_three", "full_script", "cta_block"):
            assert s.get(k)
        assert isinstance(s.get("retention_beats"), list)
        assert view["project"]["status"] in ("SCRIPT_GENERATED", "IN_PROGRESS", "GENERATING")

    def test_scenes_requires_script(self, creator_session):
        # create a separate project with no script
        p = creator_session.post(f"{BASE_URL}/api/projects", json={
            "name": "TEST_noscript", "niche": "tech",
            "topic": "Why go compiles so fast", "audience": "devs",
            "tone": "neutral", "target_duration": 120,
        }, timeout=15).json()
        r = creator_session.post(f"{BASE_URL}/api/projects/{p['id']}/generate-scenes", timeout=30)
        assert r.status_code == 400
        creator_session.delete(f"{BASE_URL}/api/projects/{p['id']}", timeout=15)

    def test_generate_scenes(self, creator_session, gen_project):
        r = creator_session.post(f"{BASE_URL}/api/projects/{gen_project['id']}/generate-scenes", timeout=180)
        assert r.status_code == 200, r.text
        view = r.json()
        assert isinstance(view["scenes"], list)
        assert len(view["scenes"]) > 0

    def test_generate_metadata(self, creator_session, gen_project):
        r = creator_session.post(f"{BASE_URL}/api/projects/{gen_project['id']}/generate-metadata", timeout=180)
        assert r.status_code == 200, r.text
        md = r.json()["metadata"]
        assert md is not None
        assert isinstance(md.get("title_options"), list)
        assert len(md["title_options"]) >= 10, f"only {len(md['title_options'])} titles"

    def test_generate_thumbnails(self, creator_session, gen_project):
        r = creator_session.post(f"{BASE_URL}/api/projects/{gen_project['id']}/generate-thumbnails", timeout=120)
        assert r.status_code == 200, r.text
        view = r.json()
        thumbs = [a for a in view["assets"] if a["asset_type"] == "thumbnail_concept"]
        assert len(thumbs) == 3

    def test_render_all_ready(self, creator_session, gen_project):
        r = creator_session.post(f"{BASE_URL}/api/projects/{gen_project['id']}/render", timeout=60)
        assert r.status_code == 200
        job = r.json()["render_job"]
        assert job["status"] in ("COMPLETED", "READY_TO_RENDER")

    def test_render_missing_artefacts(self, creator_session):
        p = creator_session.post(f"{BASE_URL}/api/projects", json={
            "name": "TEST_render_missing", "niche": "tech",
            "topic": "Some topic long enough to pass", "audience": "devs",
            "tone": "neutral", "target_duration": 60,
        }, timeout=15).json()
        r = creator_session.post(f"{BASE_URL}/api/projects/{p['id']}/render", timeout=30)
        assert r.status_code == 200
        job = r.json()["render_job"]
        assert job["status"] == "FAILED"
        assert "Missing" in (job.get("error_message") or "")
        creator_session.delete(f"{BASE_URL}/api/projects/{p['id']}", timeout=15)

    def test_patch_script_recomputes_wordcount(self, creator_session, gen_project):
        new_text = "word " * 120
        r = creator_session.patch(f"{BASE_URL}/api/projects/{gen_project['id']}/script",
                                  json={"full_script": new_text}, timeout=20)
        assert r.status_code == 200
        assert r.json()["script"]["word_count"] == 120

    def test_patch_metadata(self, creator_session, gen_project):
        r = creator_session.patch(f"{BASE_URL}/api/projects/{gen_project['id']}/metadata",
                                  json={"selected_title": "TEST selected title"}, timeout=20)
        assert r.status_code == 200
        assert r.json()["metadata"]["selected_title"] == "TEST selected title"


# ---------- Exports ----------
class TestExports:
    def test_script_txt(self, creator_session, gen_project):
        r = creator_session.get(f"{BASE_URL}/api/projects/{gen_project['id']}/export/script.txt", timeout=30)
        assert r.status_code == 200
        assert "text/plain" in r.headers.get("content-type", "")
        assert len(r.text) > 50

    def test_scenes_csv(self, creator_session, gen_project):
        r = creator_session.get(f"{BASE_URL}/api/projects/{gen_project['id']}/export/scenes.csv", timeout=30)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        assert "scene_number" in r.text or len(r.text) > 10

    def test_metadata_json(self, creator_session, gen_project):
        r = creator_session.get(f"{BASE_URL}/api/projects/{gen_project['id']}/export/metadata.json", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json().get("title_options"), list)

    def test_package_zip(self, creator_session, gen_project):
        r = creator_session.get(f"{BASE_URL}/api/projects/{gen_project['id']}/export/package.zip", timeout=30)
        assert r.status_code == 200
        assert "zip" in r.headers.get("content-type", "")
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        assert "project.json" in names
        assert "README.md" in names


# ---------- Analytics & Settings ----------
class TestAnalytics:
    def test_overview(self, creator_session):
        r = creator_session.get(f"{BASE_URL}/api/analytics/overview", timeout=20)
        assert r.status_code == 200
        for k in ("total_projects", "completed", "in_progress", "average_quality_score",
                  "total_estimated_cost", "status_counts", "niche_counts", "projects_over_time"):
            assert k in r.json(), f"missing {k}"


class TestSettings:
    def test_get_and_patch(self, creator_session):
        r = creator_session.get(f"{BASE_URL}/api/settings", timeout=15)
        assert r.status_code == 200
        assert r.json().get("preferred_provider")
        p = creator_session.patch(f"{BASE_URL}/api/settings",
                                  json={"cost_limit_monthly": 123.45}, timeout=15)
        assert p.status_code == 200
        assert abs(p.json()["cost_limit_monthly"] - 123.45) < 0.01


# ---------- Admin & RBAC ----------
class TestAdminRBAC:
    def test_admin_list_users(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/users", timeout=15)
        assert r.status_code == 200
        assert any(u["email"] == ADMIN_EMAIL for u in r.json())

    def test_admin_forbidden_for_creator(self, creator_session):
        r = creator_session.get(f"{BASE_URL}/api/admin/users", timeout=15)
        assert r.status_code == 403

    def test_patch_role(self, admin_session):
        # find an existing non-admin target by creating a TEST user first
        email = f"test_role_{uuid.uuid4().hex[:8]}@example.com"
        s = requests.Session()
        rr = s.post(f"{BASE_URL}/api/auth/register", json={
            "name": "TEST role user", "email": email, "password": "pw123456", "role": "viewer"}, timeout=15)
        assert rr.status_code == 200
        uid = rr.json()["id"]
        r = admin_session.patch(f"{BASE_URL}/api/admin/users/{uid}/role", json={"role": "editor"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["role"] == "editor"


class TestOwnershipAndViewer:
    def test_viewer_cannot_create(self):
        s = requests.Session()
        email = f"test_viewer_{uuid.uuid4().hex[:8]}@example.com"
        r = s.post(f"{BASE_URL}/api/auth/register", json={
            "name": "TEST viewer", "email": email, "password": "pw123456", "role": "viewer"}, timeout=15)
        assert r.status_code == 200
        c = s.post(f"{BASE_URL}/api/projects", json={
            "name": "x", "niche": "tech", "topic": "valid topic text here",
            "audience": "x", "tone": "y", "target_duration": 60}, timeout=15)
        assert c.status_code == 403

    def test_creator_cannot_access_other_project(self, creator_session):
        # Create a separate creator B + project, then try with creator A session
        s_b = requests.Session()
        email = f"test_crB_{uuid.uuid4().hex[:8]}@example.com"
        s_b.post(f"{BASE_URL}/api/auth/register", json={
            "name": "TEST crB", "email": email, "password": "pw123456", "role": "creator"}, timeout=15)
        p = s_b.post(f"{BASE_URL}/api/projects", json={
            "name": "TEST_B_proj", "niche": "tech",
            "topic": "A very valid topic here text",
            "audience": "devs", "tone": "neutral", "target_duration": 60}, timeout=15).json()
        r = creator_session.get(f"{BASE_URL}/api/projects/{p['id']}", timeout=15)
        assert r.status_code == 403
        s_b.delete(f"{BASE_URL}/api/projects/{p['id']}", timeout=15)


# ---------- Share Links (Phase 2) ----------

def _find_completed_project(session) -> dict | None:
    """Return the seeded COMPLETED project (has full metadata)."""
    r = session.get(f"{BASE_URL}/api/projects", timeout=15)
    r.raise_for_status()
    for p in r.json():
        if p.get("status") == "COMPLETED":
            return p
    return None


@pytest.fixture(scope="module")
def completed_project(creator_session):
    p = _find_completed_project(creator_session)
    assert p is not None, "Expected at least one seeded COMPLETED project"
    yield p
    # Cleanup: disable share so test does not leak enabled state
    try:
        creator_session.delete(f"{BASE_URL}/api/projects/{p['id']}/share", timeout=15)
    except Exception:
        pass


@pytest.fixture(scope="module")
def draft_project(creator_session):
    p = creator_session.post(f"{BASE_URL}/api/projects", json={
        "name": "TEST_share_draft", "niche": "tech",
        "topic": "A draft project that cannot be shared yet text",
        "audience": "devs", "tone": "neutral", "target_duration": 120,
    }, timeout=15).json()
    yield p
    creator_session.delete(f"{BASE_URL}/api/projects/{p['id']}", timeout=15)


class TestShareLinks:
    def test_enable_share_draft_rejected(self, creator_session, draft_project):
        r = creator_session.post(f"{BASE_URL}/api/projects/{draft_project['id']}/share",
                                 json={}, timeout=15)
        assert r.status_code == 400
        assert "shared" in r.text.lower() or "METADATA_GENERATED" in r.text

    def test_enable_share_on_completed(self, creator_session, completed_project):
        r = creator_session.post(f"{BASE_URL}/api/projects/{completed_project['id']}/share",
                                 json={}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["enabled"] is True
        assert data["token"] and len(data["token"]) >= 16
        assert "view_count" in data

    def test_project_view_contains_share_block(self, creator_session, completed_project):
        r = creator_session.get(f"{BASE_URL}/api/projects/{completed_project['id']}", timeout=15)
        assert r.status_code == 200
        share = r.json().get("share")
        assert share is not None
        assert share["enabled"] is True
        assert share["token"] is not None
        assert "view_count" in share and "last_viewed_at" in share

    def test_enable_share_with_title_override(self, creator_session, completed_project):
        r = creator_session.post(f"{BASE_URL}/api/projects/{completed_project['id']}/share",
                                 json={"title_override": "TEST override title"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["title_override"] == "TEST override title"

    def test_patch_share_clears_title(self, creator_session, completed_project):
        # set
        r = creator_session.patch(f"{BASE_URL}/api/projects/{completed_project['id']}/share",
                                  json={"title_override": "Another TEST title"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["title_override"] == "Another TEST title"
        # clear via empty string
        r2 = creator_session.patch(f"{BASE_URL}/api/projects/{completed_project['id']}/share",
                                   json={"title_override": ""}, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["title_override"] in (None, "")

    def test_public_share_anonymous_access(self, creator_session, completed_project):
        # Ensure enabled
        enable = creator_session.post(f"{BASE_URL}/api/projects/{completed_project['id']}/share",
                                      json={}, timeout=15).json()
        token = enable["token"]
        anon = requests.Session()  # no auth
        r = anon.get(f"{BASE_URL}/api/public/share/{token}", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        # Required fields
        for k in ("display_title", "status", "quality_score", "metadata", "thumbnails"):
            assert k in body, f"missing {k}"
        # private fields must NOT leak
        forbidden = {"user_id", "estimated_cost", "script", "scenes", "cta_goal", "monetisation_intent", "email", "owner_email"}
        assert not (forbidden & set(body.keys())), f"leaked fields: {forbidden & set(body.keys())}"
        # metadata sub-shape
        md = body["metadata"]
        assert md is not None
        for k in ("description", "tags", "hashtags", "chapters", "pinned_comment"):
            assert k in md

    def test_public_unknown_token_404(self):
        r = requests.get(f"{BASE_URL}/api/public/share/definitely-not-a-real-token-xx", timeout=15)
        assert r.status_code == 404

    def test_public_short_token_404(self):
        r = requests.get(f"{BASE_URL}/api/public/share/short", timeout=15)
        assert r.status_code == 404

    def test_view_count_increments(self, creator_session, completed_project):
        enable = creator_session.post(f"{BASE_URL}/api/projects/{completed_project['id']}/share",
                                      json={}, timeout=15).json()
        token = enable["token"]
        before = creator_session.get(f"{BASE_URL}/api/projects/{completed_project['id']}", timeout=15).json()["share"]["view_count"]
        # 2 anonymous hits
        for _ in range(2):
            requests.get(f"{BASE_URL}/api/public/share/{token}", timeout=15)
        time.sleep(0.3)
        after = creator_session.get(f"{BASE_URL}/api/projects/{completed_project['id']}", timeout=15).json()["share"]
        assert after["view_count"] >= before + 2
        assert after["last_viewed_at"] is not None

    def test_regenerate_rotates_token_and_resets_count(self, creator_session, completed_project):
        enable = creator_session.post(f"{BASE_URL}/api/projects/{completed_project['id']}/share",
                                      json={}, timeout=15).json()
        old_token = enable["token"]
        # Hit it once so view_count > 0
        requests.get(f"{BASE_URL}/api/public/share/{old_token}", timeout=15)
        r = creator_session.post(f"{BASE_URL}/api/projects/{completed_project['id']}/share/regenerate", timeout=15)
        assert r.status_code == 200
        new_token = r.json()["token"]
        assert new_token and new_token != old_token
        assert r.json()["view_count"] == 0
        # old token no longer works
        old = requests.get(f"{BASE_URL}/api/public/share/{old_token}", timeout=15)
        assert old.status_code == 404
        # new token works
        new = requests.get(f"{BASE_URL}/api/public/share/{new_token}", timeout=15)
        assert new.status_code == 200

    def test_disable_makes_public_404(self, creator_session, completed_project):
        enable = creator_session.post(f"{BASE_URL}/api/projects/{completed_project['id']}/share",
                                      json={}, timeout=15).json()
        token = enable["token"]
        d = creator_session.delete(f"{BASE_URL}/api/projects/{completed_project['id']}/share", timeout=15)
        assert d.status_code == 200
        assert d.json()["enabled"] is False
        # public URL now 404
        r = requests.get(f"{BASE_URL}/api/public/share/{token}", timeout=15)
        assert r.status_code == 404
        # and project view returns token: None
        pv = creator_session.get(f"{BASE_URL}/api/projects/{completed_project['id']}", timeout=15).json()
        assert pv["share"]["enabled"] is False
        assert pv["share"]["token"] is None

    def test_other_creator_forbidden(self, completed_project):
        # Register creator B
        s_b = requests.Session()
        email = f"test_share_B_{uuid.uuid4().hex[:8]}@example.com"
        rr = s_b.post(f"{BASE_URL}/api/auth/register", json={
            "name": "TEST share B", "email": email, "password": "pw123456", "role": "creator"}, timeout=15)
        assert rr.status_code == 200
        for method, path in [
            ("post", f"/api/projects/{completed_project['id']}/share"),
            ("patch", f"/api/projects/{completed_project['id']}/share"),
            ("delete", f"/api/projects/{completed_project['id']}/share"),
            ("post", f"/api/projects/{completed_project['id']}/share/regenerate"),
        ]:
            r = getattr(s_b, method)(f"{BASE_URL}{path}", json={}, timeout=15)
            assert r.status_code == 403, f"{method} {path} -> {r.status_code} expected 403"

    def test_admin_can_manage_share(self, admin_session, completed_project):
        r = admin_session.post(f"{BASE_URL}/api/projects/{completed_project['id']}/share",
                               json={}, timeout=15)
        assert r.status_code == 200
        assert r.json()["enabled"] is True
