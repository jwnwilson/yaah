"""Integration tests for work-item attachments."""
import tempfile

from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings

# Isolate blobs to an OS temp dir so tests never write into the repo's ./data.
_STORAGE_DIR = tempfile.mkdtemp(prefix="yaah-attach-test-")


def _client(**overrides):
    overrides.setdefault("storage_dir", _STORAGE_DIR)
    return TestClient(
        create_app(Settings(_env_file=None, database_url="sqlite:///:memory:", **overrides))
    )


def _project(c) -> str:
    return c.post("/projects", json={"name": "A", "repo_url": "r"}).json()["data"]["id"]


def _epic(c, pid) -> str:
    return c.post(
        f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}
    ).json()["data"]["id"]


PNG = b"\x89PNG\r\n\x1a\n\x00\x00"


def test_upload_list_download_delete():
    c = _client()
    pid = _project(c)
    wi = _epic(c, pid)

    up = c.post(
        f"/work-items/{wi}/attachments",
        files={"file": ("shot.png", PNG, "image/png")},
    )
    assert up.status_code == 200, up.text
    att = up.json()["data"]
    assert att["filename"] == "shot.png" and att["content_type"] == "image/png"
    assert att["origin"] == "human" and att["size_bytes"] == len(PNG)

    listing = c.get(f"/work-items/{wi}/attachments").json()["data"]
    assert [a["id"] for a in listing] == [att["id"]]

    dl = c.get(f"/attachments/{att['id']}")
    assert dl.status_code == 200
    assert dl.content == PNG
    assert dl.headers["content-type"].startswith("image/png")
    assert dl.headers["content-disposition"].startswith("inline")
    assert dl.headers["x-content-type-options"] == "nosniff"

    assert c.delete(f"/attachments/{att['id']}").status_code == 200
    assert c.get(f"/attachments/{att['id']}").status_code == 404


def test_markdown_is_attachment_disposition():
    c = _client()
    pid = _project(c)
    wi = _epic(c, pid)
    up = c.post(
        f"/work-items/{wi}/attachments",
        files={"file": ("notes.md", b"# hi", "text/markdown")},
    )
    att = up.json()["data"]
    dl = c.get(f"/attachments/{att['id']}")
    assert dl.headers["content-disposition"].startswith("attachment")


def test_rejects_disallowed_type():
    c = _client()
    pid = _project(c)
    wi = _epic(c, pid)
    r = c.post(
        f"/work-items/{wi}/attachments",
        files={"file": ("x.svg", b"<svg/>", "image/svg+xml")},
    )
    assert r.status_code == 415


def test_rejects_oversized():
    c = _client(max_attachment_bytes=8)
    pid = _project(c)
    wi = _epic(c, pid)
    r = c.post(
        f"/work-items/{wi}/attachments",
        files={"file": ("big.png", b"123456789", "image/png")},
    )
    assert r.status_code == 413


def test_unknown_work_item_404():
    c = _client()
    r = c.post("/work-items/nope/attachments", files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 404
