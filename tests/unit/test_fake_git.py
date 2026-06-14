from adapters.git.fake import FakeGit


def test_fake_git_records_calls_and_reports_changes():
    g = FakeGit(has_changes=True)
    g.prepare(repo_ref="/repo", workspace_path="/ws", branch="agent/t1", mode="worktree")
    assert g.prepared == [("/repo", "/ws", "agent/t1", "worktree")]
    assert g.commit_all("/ws", "msg") is True
    g.push("/ws", "agent/t1", token="tok")
    assert g.pushed == [("/ws", "agent/t1", "tok")]
    assert g.current_branch("/ws") == "agent/t1"


def test_fake_git_no_changes():
    g = FakeGit(has_changes=False)
    assert g.commit_all("/ws", "msg") is False


def test_fake_diff_returns_configured_memory_diff():
    git = FakeGit(memory_diff="diff --git a/CLAUDE.md b/CLAUDE.md")
    assert "CLAUDE.md" in git.diff("/ws", paths=["CLAUDE.md", "AGENTS.md", "docs/adr"])


def test_fake_diff_empty_by_default():
    git = FakeGit()
    assert git.diff("/ws", paths=["CLAUDE.md"]) == ""


def test_fake_commit_to_branch_records_when_memory_changed():
    git = FakeGit(memory_diff="diff --git a/CLAUDE.md b/CLAUDE.md")
    committed = git.commit_to_branch("/ws", branch="agent/memory-r1", base="main",
                                     paths=["CLAUDE.md"], message="memory")
    assert committed is True
    assert git.committed_to_branch == [
        ("/ws", "agent/memory-r1", "main", ("CLAUDE.md",), "memory")
    ]


def test_fake_commit_to_branch_noop_when_no_memory_changes():
    git = FakeGit()
    assert git.commit_to_branch("/ws", branch="b", base="main",
                                paths=["CLAUDE.md"], message="m") is False
    assert git.committed_to_branch == []


def test_fake_merge_into_base_records_and_returns_result():
    git = FakeGit(merge_ok=True)
    assert git.merge_into_base("/repo", branch="agent/memory-r1", base="main") is True
    assert git.merged_into_base == [("/repo", "agent/memory-r1", "main")]


def test_fake_merge_into_base_can_report_failure():
    git = FakeGit(merge_ok=False)
    assert git.merge_into_base("/repo", branch="b", base="main") is False
