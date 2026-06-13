class FakeSkillFetcher:
    """Records fetches; no filesystem/network. `fail_on` triggers a RuntimeError for a source."""

    def __init__(self, fail_on: str | None = None):
        self.fetched: list[tuple[str, str]] = []
        self._fail_on = fail_on

    def fetch(self, source: str, dest: str) -> None:
        if self._fail_on is not None and source == self._fail_on:
            raise RuntimeError(f"cannot fetch {source}")
        self.fetched.append((source, dest))
