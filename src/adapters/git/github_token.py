import httpx

from adapters.git.ports import ForgeError

_API = "https://api.github.com"


class GitHubTokenForge:
    """GitForgePort backed by a Personal Access Token. The token authenticates both the git
    push (HTTPS basic-auth via the shared `_auth_args`) and the PR REST call. Simpler to set up
    than a GitHub App; the token must have contents + pull-request write scope on `repo`."""

    def __init__(self, *, token: str, repo: str, base_branch: str = "main"):
        self._token = token
        self._repo = repo
        self._base_branch = base_branch

    def _client_factory(self) -> httpx.Client:  # overridden in tests
        return httpx.Client(timeout=30)

    def installation_token(self) -> str:
        # The PAT is the push credential directly — no token-minting round trip.
        return self._token

    def open_pull_request(self, *, head: str, base: str, title: str, body: str) -> str:
        with self._client_factory() as c:
            r = c.post(
                f"{_API}/repos/{self._repo}/pulls",
                headers={
                    "Authorization": f"token {self._token}",
                    "Accept": "application/vnd.github+json",
                },
                json={"head": head, "base": base, "title": title, "body": body},
            )
        if r.status_code >= 300:
            raise ForgeError(f"open PR failed: {r.status_code} {r.text[:200]}")
        return r.json()["html_url"]
