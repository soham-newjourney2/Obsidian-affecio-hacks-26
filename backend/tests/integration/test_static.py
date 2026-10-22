import pytest
from fastapi.testclient import TestClient


def test_index_served(client: TestClient) -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/html")
    assert "<title>ECHO</title>" in res.text


def test_missing_static_file_uses_error_shape(client: TestClient) -> None:
    res = client.get("/nope.css")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize(
    ("path", "content_type"),
    [
        ("/js/pages/landing.js", "text/javascript"),
        ("/css/tokens.css", "text/css"),
        ("/assets/brand/logo.svg", "image/svg+xml"),
        ("/assets/brand/favicon.svg", "image/svg+xml"),
    ],
)
def test_static_assets_have_correct_types(client: TestClient, path: str, content_type: str) -> None:
    res = client.get(path)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith(content_type)


def test_gsap_loaded_with_sri(client: TestClient) -> None:
    html = client.get("/").text
    assert 'src="https://cdnjs.cloudflare.com/ajax/libs/gsap/' in html
    assert 'integrity="sha512-' in html
    assert 'crossorigin="anonymous"' in html


def test_frontend_has_no_inner_html(client: TestClient, settings) -> None:
    scripts = sorted((settings.frontend_dir / "js").rglob("*.js"))
    assert len(scripts) >= 8
    for script in scripts:
        path = "/" + script.relative_to(settings.frontend_dir).as_posix()
        source = client.get(path).text
        assert "innerHTML" not in source and "insertAdjacentHTML" not in source, path


def test_credential_forms_cannot_leak_into_urls(client: TestClient) -> None:
    """Before JS wires them, auth forms must not be submittable as GET (password in URL)."""
    html = client.get("/auth.html").text
    for form_id in ("panel-login", "panel-register"):
        assert f'<form id="{form_id}" class="form" method="post"' in html
    assert html.count('type="submit" disabled') == 2
