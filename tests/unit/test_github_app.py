import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from adapters.forge.github_app import GitHubApp


def _pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def test_installation_token_and_pr(monkeypatch):
    pem = _pem()
    app = GitHubApp(app_id="123", private_key=pem, installation_id="456",
                    repo="o/r", base_branch="main")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/access_tokens"):
            return httpx.Response(201, json={"token": "ghs_xyz"})
        if request.url.path.endswith("/pulls"):
            return httpx.Response(201, json={"html_url": "https://github.com/o/r/pull/7"})
        return httpx.Response(404)

    monkeypatch.setattr(
        app, "_client_factory", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    assert app.installation_token() == "ghs_xyz"
    url = app.open_pull_request(head="agent/t1", base="main", title="t", body="b")
    assert url == "https://github.com/o/r/pull/7"
