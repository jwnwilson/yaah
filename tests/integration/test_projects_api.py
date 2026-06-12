from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def make_client() -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, database_url="sqlite:///:memory:")))


def test_create_get_list_update_delete_project():
    c = make_client()
    created = c.post(
        "/projects", json={"name": "llm_api", "repo_url": "https://github.com/x/llm_api"}
    )
    assert created.status_code == 201
    pid = created.json()["data"]["id"]
    assert created.json()["data"]["owner_id"] == "dev-user"

    assert c.get(f"/projects/{pid}").json()["data"]["name"] == "llm_api"
    assert len(c.get("/projects").json()["data"]) == 1

    updated = c.patch(f"/projects/{pid}", json={"autonomy": "gated_merge"})
    assert updated.json()["data"]["autonomy"] == "gated_merge"

    assert c.delete(f"/projects/{pid}").status_code == 200
    assert c.get(f"/projects/{pid}").status_code == 404


def test_create_project_requires_a_repo():
    resp = make_client().post("/projects", json={"name": "nowhere"})
    assert resp.status_code == 422


def test_list_rejects_non_dict_and_malformed_filters():
    c = make_client()
    assert c.get("/projects", params={"filters": "5"}).status_code == 400
    assert c.get("/projects", params={"filters": "[]"}).status_code == 400
    assert c.get("/projects", params={"filters": "{bad"}).status_code == 400


def test_delete_project_cascades_work_items():
    c = make_client()
    pid = c.post("/projects", json={"name": "p", "repo_url": "r"}).json()["data"]["id"]
    epic = c.post(f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}).json()["data"]

    assert c.delete(f"/projects/{pid}").status_code == 200

    assert c.patch(f"/work-items/{epic['id']}", json={"title": "x"}).status_code == 404
