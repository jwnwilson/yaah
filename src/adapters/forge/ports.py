from typing import Protocol


class ForgeError(Exception):
    """Raised when a git-forge (GitHub) operation fails."""


class GitForgePort(Protocol):
    def installation_token(self) -> str: ...
    def open_pull_request(self, *, head: str, base: str, title: str, body: str) -> str: ...
