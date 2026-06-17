import httpx

from adapters.git.github_token import GitHubTokenForge


def test_token_forge_returns_token_and_opens_pr():
    forge = GitHubTokenForge(token="ghp_abc", repo="o/r", base_branch="main")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        seen["path"] = request.url.path
        if request.url.path.endswith("/pulls"):
            return httpx.Response(201, json={"html_url": "https://github.com/o/r/pull/9"})
        return httpx.Response(404)

    forge._client_factory = lambda: httpx.Client(transport=httpx.MockTransport(handler))
    assert forge.installation_token() == "ghp_abc"  # used for git push basic-auth
    url = forge.open_pull_request(head="agent/t1", base="main", title="t", body="b")
    assert url == "https://github.com/o/r/pull/9"
    assert seen["auth"] == "token ghp_abc"
    assert seen["path"] == "/repos/o/r/pulls"
