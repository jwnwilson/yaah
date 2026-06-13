from domain import scm


def test_branch_name():
    assert scm.branch_name("abc123") == "agent/abc123"


def test_commit_message_includes_title():
    assert scm.commit_message("Add login").startswith("Add login")


def test_pr_title_and_body():
    assert scm.pr_title("Add login") == "[yaah] Add login"
    body = scm.pr_body("Add login", "do the thing", ["works", "tested"])
    assert "do the thing" in body
    assert "- works" in body and "- tested" in body
