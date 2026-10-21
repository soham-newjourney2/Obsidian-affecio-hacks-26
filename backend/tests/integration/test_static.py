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


def test_frontend_has_no_inner_html(client: TestClient) -> None:
    for path in ("/js/core/ui.js", "/js/core/fx.js", "/js/core/strings.js", "/js/pages/landing.js"):
        assert "innerHTML" not in client.get(path).text
