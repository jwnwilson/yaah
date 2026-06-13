class FakeGitForge:
    """Records token mints + PRs; returns canned values. No network."""

    def __init__(self) -> None:
        self.token_mints = 0
        self.opened: list[tuple] = []

    def installation_token(self) -> str:
        self.token_mints += 1
        return "fake-token"

    def open_pull_request(self, *, head, base, title, body) -> str:
        self.opened.append((head, base, title, body))
        return "https://github.com/fake/fake/pull/1"
