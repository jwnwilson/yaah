import shutil
import subprocess
from pathlib import Path


def _is_git_source(source: str) -> bool:
    return source.endswith(".git") or source.startswith(("git@", "http://", "https://", "ssh://"))


class SkillFetcher:
    """Fetch a granted skill's source into `dest`. Git URL -> clone; local path -> copy."""

    def fetch(self, source: str, dest: str) -> None:
        dest_path = Path(dest)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if _is_git_source(source):
            proc = subprocess.run(
                ["git", "clone", "--depth", "1", source, dest],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.strip() or "skill clone failed")
        else:
            if dest_path.exists():
                shutil.rmtree(dest_path)
            shutil.copytree(source, dest)
