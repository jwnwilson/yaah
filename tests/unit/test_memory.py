from domain.memory import MEMORY_PATHS, changed_files


def test_memory_paths_are_the_bounded_set():
    assert "CLAUDE.md" in MEMORY_PATHS
    assert "AGENTS.md" in MEMORY_PATHS
    assert "docs/adr" in MEMORY_PATHS


def test_changed_files_parses_unified_diff():
    diff = (
        "diff --git a/CLAUDE.md b/CLAUDE.md\n"
        "--- a/CLAUDE.md\n"
        "+++ b/CLAUDE.md\n"
        "@@ -1 +1,2 @@\n"
        " x\n+y\n"
        "diff --git a/docs/adr/0001.md b/docs/adr/0001.md\n"
        "--- /dev/null\n"
        "+++ b/docs/adr/0001.md\n"
        "@@ -0,0 +1 @@\n+new\n"
    )
    assert changed_files(diff) == ["CLAUDE.md", "docs/adr/0001.md"]


def test_changed_files_empty_for_empty_diff():
    assert changed_files("") == []
