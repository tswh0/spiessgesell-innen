import io
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app

CATEGORIES = """
- key: bread
  label: Brot
  hint: frisch
- key: meat
  label: Fleisch
  hint: saftig
- key: sauce
  label: Sauce
  hint: knoblauch
"""


@pytest.fixture()
def app(tmp_path: Path):
    categories = tmp_path / "categories.yaml"
    categories.write_text(CATEGORIES, encoding="utf-8")
    settings = Settings(
        data_dir=tmp_path / "data",
        secret_key="test-secret",
        shared_password="geheim",
        base_url="http://testserver",
        categories_file=categories,
    )
    return create_app(settings)


@pytest.fixture()
def browser(app):
    return TestClient(app)


def csrf(client: TestClient, path: str = "/login") -> str:
    page = client.get(path).text
    match = re.search(r'name="csrf" value="([^"]+)"', page)
    assert match
    return match.group(1)


def login(client: TestClient, name: str = "Tom") -> None:
    token = csrf(client)
    response = client.post(
        "/login",
        data={"csrf": token, "password": "geheim", "next": "/"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    token = csrf(client, "/wer")
    response = client.post(
        "/wer",
        data={"csrf": token, "name": name, "next": "/"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def jpeg(width: int = 800, height: int = 600) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (180, 90, 40)).save(buffer, "JPEG")
    return buffer.getvalue()


def add_shop(client: TestClient, name: str = "Test Döner") -> str:
    token = csrf(client, "/laeden/neu")
    response = client.post(
        "/laeden/neu",
        data={
            "csrf": token,
            "name": name,
            "link": "52.5100,13.4200",
            "address": "Teststraße 1, Berlin",
            "district": "Mitte",
            "note": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    return response.headers["location"].rsplit("/", 1)[-1]


def review_payload(token: str, scores=None, body="Guter Döner.") -> dict:
    scores = scores or {"bread": 8, "meat": 9, "sauce": 7}
    data = {
        "csrf": token,
        "visited_on": "2026-11-01",
        "price": "7,50",
        "body": body,
    }
    for key, value in scores.items():
        data[f"score_{key}"] = str(value)
    return data


def test_login_required(browser: TestClient):
    response = browser.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_wrong_password(browser: TestClient):
    token = csrf(browser)
    response = browser.post(
        "/login",
        data={"csrf": token, "password": "falsch", "next": "/"},
    )
    assert response.status_code == 401
    assert "Falsches Passwort" in response.text


def test_full_flow(browser: TestClient, app):
    login(browser)
    slug = add_shop(browser)
    assert slug == "test-doener"

    token = csrf(browser, f"/laden/{slug}/bewerten")
    response = browser.post(
        f"/laden/{slug}/bewerten",
        data=review_payload(token),
        files={"photos": ("doener.jpg", jpeg(), "image/jpeg")},
        follow_redirects=False,
    )
    assert response.status_code == 303

    shop = browser.get(f"/laden/{slug}").text
    assert "Test Döner" in shop
    assert "8,0" in shop
    assert "/uploads/thumbs/" in shop

    uploads = app.state.settings.uploads_dir
    assert len(list(uploads.glob("*.webp"))) == 1
    assert len(list((uploads / "thumbs").glob("*.webp"))) == 1

    ranking = browser.get("/rangliste").text
    assert "Test Döner" in ranking
    assert "8,0" in ranking


def test_scores_are_required(browser: TestClient):
    login(browser)
    slug = add_shop(browser, "Ohne Punkte")
    token = csrf(browser, f"/laden/{slug}/bewerten")
    response = browser.post(
        f"/laden/{slug}/bewerten",
        data={"csrf": token, "visited_on": "2026-11-01", "body": "x", "score_bread": "8"},
    )
    assert response.status_code == 400
    assert "Noch Punkte" in response.text


def test_csrf_required(browser: TestClient):
    login(browser)
    slug = add_shop(browser, "CSRF")
    response = browser.post(
        f"/laden/{slug}/bewerten",
        data={"csrf": "wrong", "visited_on": "2026-11-01", "score_bread": "8",
              "score_meat": "8", "score_sauce": "8"},
    )
    assert response.status_code == 400
    assert "Sitzung abgelaufen" in response.text


def test_edit_and_delete(browser: TestClient):
    login(browser)
    slug = add_shop(browser, "Bearbeiten")
    token = csrf(browser, f"/laden/{slug}/bewerten")
    browser.post(f"/laden/{slug}/bewerten", data=review_payload(token), follow_redirects=False)

    token = csrf(browser, "/bewertungen/1/bearbeiten")
    response = browser.post(
        "/bewertungen/1",
        data=review_payload(token, {"bread": 10, "meat": 10, "sauce": 10}),
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "10,0" in browser.get(f"/laden/{slug}").text

    token = csrf(browser, "/wer")
    response = browser.post(
        "/bewertungen/1/loeschen",
        data={"csrf": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "Noch keine Bewertung" in browser.get(f"/laden/{slug}").text


def test_other_author_cannot_edit(browser: TestClient, app):
    login(browser)
    slug = add_shop(browser, "Fremd")
    token = csrf(browser, f"/laden/{slug}/bewerten")
    browser.post(f"/laden/{slug}/bewerten", data=review_payload(token), follow_redirects=False)

    token = csrf(browser, "/wer")
    browser.post("/wer", data={"csrf": token, "name": "Anna", "next": "/"}, follow_redirects=False)
    response = browser.get("/bewertungen/1/bearbeiten")
    assert response.status_code == 404


def test_rejects_bad_image(browser: TestClient):
    login(browser)
    slug = add_shop(browser, "Bild")
    token = csrf(browser, f"/laden/{slug}/bewerten")
    response = browser.post(
        f"/laden/{slug}/bewerten",
        data=review_payload(token),
        files={"photos": ("evil.jpg", b"not an image", "image/jpeg")},
    )
    assert response.status_code == 400
    assert "kein lesbares Bild" in response.text


def test_uploads_require_login(browser: TestClient, app):
    login(browser)
    slug = add_shop(browser, "Privat")
    token = csrf(browser, f"/laden/{slug}/bewerten")
    browser.post(
        f"/laden/{slug}/bewerten",
        data=review_payload(token),
        files={"photos": ("doener.jpg", jpeg(), "image/jpeg")},
        follow_redirects=False,
    )
    file = next(app.state.settings.uploads_dir.glob("*.webp")).name
    assert browser.get(f"/uploads/{file}").status_code == 200

    anonymous = TestClient(app)
    response = anonymous.get(f"/uploads/{file}", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_unknown_shop(browser: TestClient):
    login(browser)
    assert browser.get("/laden/gibts-nicht").status_code == 404
