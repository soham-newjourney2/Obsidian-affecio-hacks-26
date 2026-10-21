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
