"""The deployed Project URL must serve the product, not a JSON 404.

The console was previously unreachable in deployment: not copied into the
image, not mounted by the app, and pointed at a hardcoded localhost origin.
These tests pin all three so a judge opening the Cloud Run URL sees the
console and the API keeps working underneath it.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from nadi.api.app import FRONTEND_DIR, app

client = TestClient(app)
REPO_ROOT = Path(__file__).resolve().parents[1]


def test_frontend_dir_resolves_to_the_repo_console():
    """Guards the parents[3] hop. In the container the package lives at
    /app/src/nadi/api/app.py and the console at /app/frontend, so this
    relative resolution is what makes `COPY frontend ./frontend` line up."""
    assert FRONTEND_DIR == REPO_ROOT / "frontend"
    assert FRONTEND_DIR.is_dir()
    assert (FRONTEND_DIR / "index.html").is_file()


def test_root_serves_the_console_html():
    res = client.get("/")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/html")
    assert "<!DOCTYPE html>" in res.text or "<!doctype html>" in res.text


def test_static_assets_are_served():
    for path, ctype in (("/style.css", "text/css"), ("/app.js", "javascript")):
        res = client.get(path)
        assert res.status_code == 200, f"{path} not served"
        assert ctype in res.headers["content-type"]


def test_mount_does_not_shadow_the_api():
    """StaticFiles is mounted at "/" and would swallow everything if it were
    registered before the routes. Registration order is the only thing
    keeping these alive."""
    assert client.get("/health").status_code == 200
    assert client.get("/health").json()["ave_enabled"] is False
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200

    res = client.get("/v1/workspaces/ws_aurora/mentions", headers={"X-Nadi-Role": "ws_admin"})
    assert res.status_code == 200
    assert res.json()["items"]


def test_console_uses_a_same_origin_api_base():
    """A hardcoded host here pointed the deployed console at the viewer's own
    machine, so every request failed for anyone but the developer."""
    js = (FRONTEND_DIR / "app.js").read_text(encoding="utf-8")
    config = js[: js.index("const WS_ID")]

    # The only absolute origin permitted in the API base config is the
    # explicit file:// development fallback.
    origins = re.findall(r"https?://[^\s'\"`]+", config)
    assert origins == ["http://localhost:8080"], f"unexpected hardcoded origin(s): {origins}"
    assert "window.location.protocol" in config
