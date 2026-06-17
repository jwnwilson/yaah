from domain.memory import MemoryProposal, MemoryProposalStatus


def test_memory_proposal_defaults():
    p = MemoryProposal(owner_id="u", run_id="r", project_id="p", branch="agent/memory-r")
    assert len(p.id) == 32
    assert p.status == MemoryProposalStatus.PROPOSED
    assert p.diff == ""
    assert p.files == []
    assert p.pr_url is None
    assert p.resolved_at is None
    assert p.created_at is not None


def test_memory_proposal_carries_diff_and_files():
    p = MemoryProposal(owner_id="u", run_id="r", project_id="p", branch="b",
                       diff="diff --git a/CLAUDE.md b/CLAUDE.md", files=["CLAUDE.md"])
    assert p.files == ["CLAUDE.md"]
    assert "CLAUDE.md" in p.diff
