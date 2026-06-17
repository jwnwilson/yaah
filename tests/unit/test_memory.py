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


def test_role_memory_digest_bounds_and_order():
    from domain.agent.models import AgentRole
    from domain.memory import RoleMemoryEntry, role_memory_digest
    entries = [RoleMemoryEntry(owner_id="u1", role=AgentRole.BACKEND, content=f"note {i}")
               for i in range(5)]
    out = role_memory_digest(entries, max_entries=3, max_chars=10_000)
    assert out == "- note 0\n- note 1\n- note 2"
    big = [RoleMemoryEntry(owner_id="u1", role=AgentRole.BACKEND, content="x" * 50)
           for _ in range(5)]
    capped = role_memory_digest(big, max_entries=5, max_chars=60)
    assert capped.count("\n") == 0  # only the first entry fits
    assert role_memory_digest([], max_entries=3, max_chars=100) == ""
