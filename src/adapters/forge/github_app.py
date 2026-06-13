import time
from pathlib import Path

import httpx
import jwt

from adapters.forge.ports import ForgeError

_API = "https://api.github.com"


class GitHubApp:
    """GitForgePort backed by a GitHub App. Mints short-lived installation tokens
    (never persisted) and opens PRs. Creds come from Settings/env."""

    def __init__(self, *, app_id: str, private_key: str, installation_id: str,
                 repo: str, base_branch: str = "main"):
        self._app_id = app_id
        self._key = (
            Path(private_key).read_text()
            if "\n" not in private_key and Path(private_key).exists()
            else private_key
        )
        self._installation_id = installation_id
        self._repo = repo
        self._base_branch = base_branch

    def _client_factory(self) -> httpx.Client:  # overridden in tests
        return httpx.Client(timeout=30)

    def _app_jwt(self) -> str:
        now = int(time.time())
        return jwt.encode(
            {"iat": now - 60, "exp": now + 540, "iss": self._app_id},
            self._key,
            algorithm="RS256",
        )

    def installation_token(self) -> str:
        with self._client_factory() as c:
            r = c.post(
                f"{_API}/app/installations/{self._installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {self._app_jwt()}",
                    "Accept": "application/vnd.github+json",
                },
            )
        if r.status_code >= 300:
            raise ForgeError(f"token mint failed: {r.status_code}")
        return r.json()["token"]

    def open_pull_request(self, *, head: str, base: str, title: str, body: str) -> str:
        token = self.installation_token()
        with self._client_factory() as c:
            r = c.post(
                f"{_API}/repos/{self._repo}/pulls",
                headers={
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github+json",
                },
                json={"head": head, "base": base, "title": title, "body": body},
            )
        if r.status_code >= 300:
            raise ForgeError(f"open PR failed: {r.status_code} {r.text[:200]}")
        return r.json()["html_url"]
