import shutil
import tempfile

from domain.workspace import Workspace


class LocalTempWorkspace:
    """A3 stub: a throwaway temp directory per run (no real git/clone)."""

    def provision(self, run_id: str) -> Workspace:
        path = tempfile.mkdtemp(prefix=f"yaah-run-{run_id}-")
        return Workspace(run_id=run_id, path=path)

    def destroy(self, workspace: Workspace) -> None:
        shutil.rmtree(workspace.path, ignore_errors=True)
