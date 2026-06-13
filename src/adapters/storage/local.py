import shutil
from pathlib import Path


class LocalStorageAdapter:
    """Filesystem StoragePort: keys resolve under base_dir. Swap for S3 later
    with no caller changes."""

    def __init__(self, base_dir: str | Path = "data") -> None:
        self._base = Path(base_dir)

    def _resolve(self, key: str) -> Path:
        return self._base / key

    def local_path(self, key: str) -> str:
        path = self._resolve(key)
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def write_bytes(self, key: str, content: bytes) -> None:
        dest = self._resolve(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)

    def read_text(self, key: str, *, encoding: str = "utf-8") -> str:
        path = self._resolve(key)
        return path.read_text(encoding=encoding) if path.exists() else ""

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()

    def delete(self, key: str) -> None:
        self._resolve(key).unlink(missing_ok=True)

    def delete_directory(self, prefix: str) -> None:
        target = self._resolve(prefix.rstrip("/"))
        if target.exists():
            shutil.rmtree(target)
