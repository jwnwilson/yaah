from adapters.git.fake import FakeGitForge


def test_fake_forge_token_and_pr():
    f = FakeGitForge()
    assert f.installation_token() == "fake-token"
    url = f.open_pull_request(head="agent/t1", base="main", title="t", body="b")
    assert url == "https://github.com/fake/fake/pull/1"
    assert f.opened == [("agent/t1", "main", "t", "b")]
