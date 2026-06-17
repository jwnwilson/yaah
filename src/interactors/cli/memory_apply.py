"""Apply an approved memory proposal: local fast-forward merge or remote PR.

Shared by the apply endpoint (human apply) and capture_memory (auto-apply in
full_auto). Pure routing over injected GitPort / GitForgePort; returns an updated
(immutable) MemoryProposal — the caller persists it.
"""

from domain.base import utc_now
from domain.memory import MemoryProposal, MemoryProposalStatus


class MemoryApplier:
    def __init__(self, git, forge, *, profile: str) -> None:
        self._git = git
        self._forge = forge
        self._profile = profile

    def apply(self, proposal: MemoryProposal, *, repo_ref: str, base: str) -> MemoryProposal:
        if self._profile == "remote":
            pr_url = self._forge.open_pull_request(
                head=proposal.branch, base=base,
                title=f"memory update for run {proposal.run_id}",
                body="Automated project-memory update.")
            return proposal.model_copy(update={
                "status": MemoryProposalStatus.APPLIED,
                "pr_url": pr_url,
                "resolved_at": utc_now(),
            })
        self._git.merge_into_base(repo_ref, branch=proposal.branch, base=base)
        return proposal.model_copy(update={
            "status": MemoryProposalStatus.APPLIED,
            "resolved_at": utc_now(),
        })
