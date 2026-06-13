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
