"""HTTP-слой (ТЗ 9)."""

from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient

from app import raster
from app.excel_template import build as build_template
from app.main import app
from app.settings_model import default_settings
from conftest import VALID_ROWS, make_workbook


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def payload(rows, settings=None):
    return {
        "rows": [
            {
                "key": row[0], "label": row[1], "unit": row[2], "min": row[3], "max": row[4],
                "current": row[5], "prev": row[6], "decimals": row[7], "inverted": row[8],
            }
            for row in rows
        ],
        "meta": {"as_of": "2026-03-12"},
        "settings": (settings or default_settings()).model_dump(),
    }


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_version_reports_fonts_and_rasterizer(client):
    body = client.get("/api/version").json()
    assert body["settingsVersion"] == 1
    assert {item["family"] for item in body["fonts"]} == {"Arimo", "Inter"}


def test_template_downloads(client):
    response = client.get("/api/template.xlsx")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert response.content[:2] == b"PK"


def test_parse_roundtrip(client):
    response = client.post(
        "/api/data/parse",
        files={"file": ("t.xlsx", build_template(), "application/vnd.ms-excel")},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["ok"] is True
    assert len(body["rows"]) == 5
    assert body["meta"]["as_of"]


def test_parse_returns_422_with_envelope(client):
    broken = make_workbook([["imoex", "Индекс", "п.", 100, 50, 75, 70, 0, False]])
    response = client.post("/api/data/parse", files={"file": ("bad.xlsx", broken, "app/x")})
    assert response.status_code == 422
    body = response.json()
    assert body["ok"] is False
    assert body["errors"] and all({"level", "where", "message"} <= set(e) for e in body["errors"])


def test_settings_schema_drives_the_form(client):
    schema = client.get("/api/settings/schema").json()
    assert schema["$defs"]["Colors"]["properties"]["current"]["format"] == "color"
    assert schema["properties"]["canvas"]["title"] == "Холст"


def test_settings_validate_rejects_unknown_version(client):
    body = default_settings().model_dump()
    body["version"] = 7
    response = client.post("/api/settings/validate", json=body)
    assert response.status_code == 422
    assert "версии 7" in response.json()["errors"][0]["message"]


def test_settings_validate_rejects_broken_json(client):
    response = client.post(
        "/api/settings/validate",
        content=b"{ not json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert "JSON" in response.json()["errors"][0]["message"]


def test_palette_endpoint(client):
    body = client.get("/api/palette").json()
    assert body["colors"]
    assert all(item["name"] for item in body["colors"])


def test_presets_listing_excludes_palette(client):
    names = [item["name"] for item in client.get("/api/presets").json()["presets"]]
    assert "palette" not in names
    assert "default" in names


def test_preset_name_traversal_is_rejected(client):
    response = client.get("/api/presets/..%2F..%2Fetc%2Fpasswd")
    assert response.status_code in (404, 422)


@pytest.mark.skipif(not raster.available(), reason="растеризатор недоступен")
def test_render_png(client):
    response = client.post("/api/render/png", json=payload(VALID_ROWS))
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG")
    assert int(response.headers["X-Required-Height"]) > 0
    warnings = json.loads(base64.b64decode(response.headers["X-Render-Warnings"]))
    assert isinstance(warnings, list)


@pytest.mark.skipif(not raster.available(), reason="растеризатор недоступен")
def test_png_is_identical_across_requests(client):
    body = payload(VALID_ROWS)
    first = client.post("/api/render/png", json=body).content
    second = client.post("/api/render/png", json=body).content
    assert first == second


def test_render_revalidates_rows(client):
    """ТЗ 9: фронтенд может прислать что угодно — ответ 422, а не 500."""
    bad = payload([["imoex", "Индекс", "п.", 100, 200, 500, 150, 0, False]])
    response = client.post("/api/render/png", json=bad)
    assert response.status_code == 422
    assert "выше годового максимума" in response.json()["errors"][0]["message"]


def test_render_svg_has_embedded_fonts(client):
    response = client.post("/api/render/svg", json=payload(VALID_ROWS))
    assert response.status_code == 200
    assert "@font-face" in response.text
    assert "base64" in response.text
    assert "gde-my-nahodimsya-2026-03-12.svg" in response.headers["content-disposition"]


def test_oversized_request_is_rejected(client):
    response = client.post(
        "/api/data/parse",
        files={"file": ("big.xlsx", b"0" * (3 * 1024 * 1024), "app/x")},
    )
    assert response.status_code == 413
