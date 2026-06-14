"""Project-memory paths and diff helpers. Pure; no I/O."""

# The bounded set the harness captures and commits. Curator edits outside these
# paths are ignored (structural blast-radius guard).
MEMORY_PATHS: list[str] = ["CLAUDE.md", "AGENTS.md", "docs/adr"]

_NEW_FILE_MARKER = "+++ b/"


def changed_files(diff: str) -> list[str]:
    """Paths from the '+++ b/<path>' lines of a unified diff, in order."""
    files: list[str] = []
    for line in diff.splitlines():
        if line.startswith(_NEW_FILE_MARKER):
            files.append(line[len(_NEW_FILE_MARKER):])
    return files
