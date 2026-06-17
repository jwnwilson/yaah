from adapters.git.fake import FakeGit, FakeGitForge
from domain.agent.memory import MemoryProposal, MemoryProposalStatus
from interactors.cli.memory_apply import MemoryApplier


def _proposal() -> MemoryProposal:
    return MemoryProposal(owner_id="u", run_id="r1", project_id="p1",
                          branch="agent/memory-r1", files=["CLAUDE.md"])


def test_local_apply_merges_into_base():
    git = FakeGit()
    applier = MemoryApplier(git, FakeGitForge(), profile="local")
    applied = applier.apply(_proposal(), repo_ref="/repo", base="main")
    assert applied.status == MemoryProposalStatus.APPLIED
    assert applied.pr_url is None
    assert applied.resolved_at is not None
    assert git.merged_into_base == [("/repo", "agent/memory-r1", "main")]


def test_remote_apply_opens_pull_request():
    git = FakeGit()
    forge = FakeGitForge()
    applier = MemoryApplier(git, forge, profile="remote")
    applied = applier.apply(_proposal(), repo_ref="ignored", base="main")
    assert applied.status == MemoryProposalStatus.APPLIED
    assert applied.pr_url == "https://github.com/fake/fake/pull/1"
    assert git.merged_into_base == []  # remote does not merge locally
    assert forge.opened and forge.opened[0][0] == "agent/memory-r1"
