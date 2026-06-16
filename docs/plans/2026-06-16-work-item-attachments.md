# Work-Item Attachments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user upload files (images, `.md`, `.txt`) to any work item and view/download them in the ticket panel — images preview inline, other files are download links.

**Architecture:** Hexagonal. Pure allowlist/sanitization/key-builder logic in `domain/`; blob bytes in the existing `StoragePort` (`LocalStorageAdapter`); metadata in a new owner-scoped `work_item_attachments` table; an authed download route serves bytes with safe headers. The data model carries an `origin` field (`"human"` now) so a later cycle can add `origin="agent"` artifacts without migration.

**Tech Stack:** Python 3.12 · FastAPI (multipart `UploadFile`) · Pydantic v2 · SQLAlchemy 2.0 + Alembic (Postgres; SQLite in-memory for tests) · pytest + httpx · React + Vite + TanStack Query · vitest + msw. Package managers: `uv` (backend), `pnpm` (UI, from `ui/`).

**Reference spec:** `docs/specs/2026-06-16-work-item-attachments-design.md`

**Conventions:** `{success,data,error}` envelope via `interactors.api.envelope.ok`. Pydantic models immutable (`model_copy`). Owner-scoping enforced by the UnitOfWork required filter. New tables: ORM row → domain model → repository in `repositories.py` → UoW property in `uow.py` → Alembic migration. Backend tests: `uv run pytest`; coverage gate `make coverage` (80%); `make lint`. UI tests: `cd ui && pnpm vitest run <path>` (never `pnpm test -- <path>`).

---

## File Structure

**Backend**
- Create `src/domain/attachments.py` — pure: allowlist, `sanitize_filename`, `canonical_extension`, `attachment_storage_key`, `is_inline_image`.
- Modify `src/domain/models.py` — add `WorkItemAttachment` model.
- Modify `src/adapters/storage/ports.py` + `src/adapters/storage/local.py` — add `read_bytes`.
- Modify `src/adapters/database/orm.py` — add `WorkItemAttachmentRow`.
- Modify `src/adapters/database/repositories.py` — add `WorkItemAttachmentRepository`.
- Modify `src/adapters/database/uow.py` — add `work_item_attachments` property.
- Create `migrations/versions/attach01_work_item_attachments.py` — Alembic migration.
- Modify `src/interactors/api/settings.py` — add `storage_dir`, `max_attachment_bytes`.
- Modify `src/interactors/api/deps.py` — add `storage` provider.
- Create `src/interactors/api/routes/attachments.py` — upload/list/download/delete.
- Modify `src/interactors/api/app.py` — register the router.

**Backend tests**
- Create `tests/unit/test_attachments_domain.py`
- Modify `tests/unit/test_local_storage.py` (add `read_bytes` test)
- Create `tests/unit/test_attachment_repository.py`
- Create `tests/integration/test_attachments_api.py`

**Frontend** (under `ui/src/`)
- Modify `lib/api/client.ts` — add `apiPostForm`.
- Create `lib/api/attachments.ts`.
- Create `modules/work-items/useAttachments.ts`.
- Modify `modules/work-items/TicketPanel.tsx` — Attachments section.
- Create `modules/work-items/Attachments.tsx` (the section component, keeps TicketPanel small).

**Frontend tests**
- Create `modules/work-items/Attachments.test.tsx`

---

## Task 1: Domain — attachment model + pure helpers

**Files:**
- Create: `src/domain/attachments.py`
- Modify: `src/domain/models.py`
- Test: `tests/unit/test_attachments_domain.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_attachments_domain.py
"""Unit tests for pure attachment policy."""
from domain.attachments import (
    ALLOWED_ATTACHMENT_TYPES,
    attachment_storage_key,
    canonical_extension,
    is_inline_image,
    sanitize_filename,
)
from domain.models import WorkItemAttachment


def test_canonical_extension_accepts_allowlisted():
    assert canonical_extension("photo.PNG") == "png"
    assert canonical_extension("notes.md") == "md"
    assert canonical_extension("a.jpeg") == "jpeg"


def test_canonical_extension_rejects_others():
    assert canonical_extension("evil.svg") is None
    assert canonical_extension("evil.exe") is None
    assert canonical_extension("noext") is None


def test_sanitize_filename_strips_path_and_unsafe_chars():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("a b/c?.png") == "c_.png"
    assert sanitize_filename("") == "file"


def test_storage_key_uses_ids_not_filename():
    key = attachment_storage_key("wi123", "att456", "png")
    assert key == "attachments/wi123/att456.png"


def test_is_inline_image():
    assert is_inline_image("image/png") is True
    assert is_inline_image("text/markdown") is False


def test_attachment_model_defaults_origin_human():
    a = WorkItemAttachment(
        owner_id="u", work_item_id="wi", filename="a.png",
        content_type="image/png", size_bytes=3, storage_key="attachments/wi/x.png",
    )
    assert a.origin == "human" and a.id and a.created_at


def test_allowlist_excludes_svg():
    assert "svg" not in ALLOWED_ATTACHMENT_TYPES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_attachments_domain.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'domain.attachments'`.

- [ ] **Step 3: Create `src/domain/attachments.py`**

```python
"""Pure attachment policy: allowlist, filename sanitization, storage-key builder. No I/O."""
import re

# ext -> canonical MIME. Single source of truth for what may be uploaded. SVG/HTML are
# excluded: inline-served SVG/HTML is an XSS vector, and only raster images render inline.
ALLOWED_ATTACHMENT_TYPES: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "md": "text/markdown",
    "txt": "text/plain",
}

INLINE_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}

_UNSAFE = re.compile(r"[^A-Za-z0-9._ -]")


def sanitize_filename(name: str) -> str:
    """Strip directory components and unsafe characters; keep a readable display name."""
    base = name.replace("\\", "/").split("/")[-1].strip()
    base = _UNSAFE.sub("_", base)
    base = base.lstrip(".") or "file"
    return base[:200]


def canonical_extension(filename: str) -> str | None:
    """The allowlisted extension for this filename, or None if not allowed."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext if ext in ALLOWED_ATTACHMENT_TYPES else None


def attachment_storage_key(work_item_id: str, attachment_id: str, ext: str) -> str:
    """Blob key built from ids + validated ext only — never the raw filename."""
    return f"attachments/{work_item_id}/{attachment_id}.{ext}"


def is_inline_image(content_type: str) -> bool:
    return content_type in INLINE_IMAGE_TYPES
```

- [ ] **Step 4: Add the `WorkItemAttachment` model to `src/domain/models.py`**

Add this class immediately after the `WorkItem` class (it uses the existing `BaseModel`, `Field`, `new_id`, `utc_now`, `datetime` already imported at the top of the file):

```python
class WorkItemAttachment(BaseModel):
    id: str = Field(default_factory=new_id)
    owner_id: str
    work_item_id: str
    filename: str
    content_type: str
    size_bytes: int
    storage_key: str
    origin: str = "human"
    created_at: datetime = Field(default_factory=utc_now)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_attachments_domain.py -v`
Expected: PASS (7 passed).

- [ ] **Step 6: Commit**

```bash
git add src/domain/attachments.py src/domain/models.py tests/unit/test_attachments_domain.py
git commit -m "feat: attachment domain model + pure policy helpers"
```

---

## Task 2: Storage — add `read_bytes`

**Files:**
- Modify: `src/adapters/storage/ports.py`, `src/adapters/storage/local.py`
- Test: `tests/unit/test_local_storage.py`

- [ ] **Step 1: Append the failing test to `tests/unit/test_local_storage.py`**

```python
def test_read_bytes_round_trips(tmp_path):
    from adapters.storage.local import LocalStorageAdapter

    s = LocalStorageAdapter(base_dir=tmp_path)
    s.write_bytes("attachments/wi/x.png", b"\x89PNG\r\n")
    assert s.read_bytes("attachments/wi/x.png") == b"\x89PNG\r\n"
```

(If `tests/unit/test_local_storage.py` does not exist, create it with this single test and the import at top: `import pytest` is not required.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_local_storage.py::test_read_bytes_round_trips -v`
Expected: FAIL — `AttributeError: 'LocalStorageAdapter' object has no attribute 'read_bytes'`.

- [ ] **Step 3: Add `read_bytes` to the port and the local adapter**

In `src/adapters/storage/ports.py`, add this line to the `StoragePort` protocol (after `read_text`):

```python
    def read_bytes(self, key: str) -> bytes: ...
```

In `src/adapters/storage/local.py`, add this method to `LocalStorageAdapter` (after `read_text`):

```python
    def read_bytes(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_local_storage.py::test_read_bytes_round_trips -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/adapters/storage/ports.py src/adapters/storage/local.py tests/unit/test_local_storage.py
git commit -m "feat: StoragePort.read_bytes for binary reads"
```

---

## Task 3: Persistence — ORM row, repository, UoW, migration

**Files:**
- Modify: `src/adapters/database/orm.py`, `src/adapters/database/repositories.py`, `src/adapters/database/uow.py`
- Create: `migrations/versions/attach01_work_item_attachments.py`
- Test: `tests/unit/test_attachment_repository.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_attachment_repository.py
"""Repository + owner-scoping for work-item attachments (SQLite in-memory)."""
from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from domain.errors import RecordNotFound
from domain.models import WorkItemAttachment
import pytest


def _uow(owner: str) -> SqlUnitOfWork:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return SqlUnitOfWork(make_session_factory(engine), required_filters={"owner_id": owner})


def test_create_list_get_delete_owner_scoped():
    uow = _uow("alice")
    with uow.transaction():
        a = uow.work_item_attachments.create(
            WorkItemAttachment(
                owner_id="alice", work_item_id="wi1", filename="a.png",
                content_type="image/png", size_bytes=4, storage_key="attachments/wi1/a.png",
            )
        )
    with uow.transaction():
        listed = uow.work_item_attachments.list(filters={"work_item_id": "wi1"}).results
        assert [x.id for x in listed] == [a.id]
        got = uow.work_item_attachments.get(a.id)
        assert got.filename == "a.png"
    with uow.transaction():
        uow.work_item_attachments.delete(a.id)
    with uow.transaction(), pytest.raises(RecordNotFound):
        uow.work_item_attachments.get(a.id)
```

NOTE: this SQLite-backed test exercises the ORM row (created via `Base.metadata.create_all`), repository, and UoW property. The Postgres migration is verified separately in Step 5.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_attachment_repository.py -v`
Expected: FAIL — `AttributeError: 'SqlUnitOfWork' object has no attribute 'work_item_attachments'`.

- [ ] **Step 3: Add the ORM row, repository, and UoW property**

In `src/adapters/database/orm.py`, add this class after `WorkItemRow` (imports `String`, `Integer`, `Text`, `DateTime`, `Mapped`, `mapped_column`, `datetime` are already at the top):

```python
class WorkItemAttachmentRow(Base):
    __tablename__ = "work_item_attachments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    work_item_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(400), nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="human")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

In `src/adapters/database/repositories.py`: add `WorkItemAttachmentRow` to the `from adapters.database.orm import (...)` block, add `WorkItemAttachment` to the `from domain.models import (...)` block, and add this repository class (e.g. after `WorkItemRepository`):

```python
class WorkItemAttachmentRepository(SqlRepository[WorkItemAttachment]):
    orm_model = WorkItemAttachmentRow
    dto = WorkItemAttachment
    default_order_by = "created_at"
```

In `src/adapters/database/uow.py`: add `WorkItemAttachmentRepository` to the `from adapters.database.repositories import (...)` block, and add this property (e.g. after the `work_items` property):

```python
    @property
    def work_item_attachments(self) -> WorkItemAttachmentRepository:
        return WorkItemAttachmentRepository(self.session, self._required_filters)
```

- [ ] **Step 4: Run repository test to verify it passes**

Run: `uv run pytest tests/unit/test_attachment_repository.py -v`
Expected: PASS.

- [ ] **Step 5: Create the Alembic migration**

First confirm the current head:

Run: `uv run alembic heads`
Expected: a single head (`orch1msg01`). If it differs, use that value as `down_revision` below.

Create `migrations/versions/attach01_work_item_attachments.py`:

```python
"""work_item_attachments table

Revision ID: attach01
Revises: orch1msg01
Create Date: 2026-06-16 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "attach01"
down_revision: str | None = "orch1msg01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "work_item_attachments",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("work_item_id", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=300), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=400), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        op.f("ix_work_item_attachments_owner_id"), "work_item_attachments", ["owner_id"]
    )
    op.create_index(
        op.f("ix_work_item_attachments_work_item_id"),
        "work_item_attachments",
        ["work_item_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_work_item_attachments_work_item_id"), "work_item_attachments")
    op.drop_index(op.f("ix_work_item_attachments_owner_id"), "work_item_attachments")
    op.drop_table("work_item_attachments")
```

- [ ] **Step 6: Verify migrations still form a single head and the existing migration test passes**

Run: `uv run alembic heads`
Expected: single head `attach01`.

Run: `uv run pytest tests/unit/test_migrations.py -v`
Expected: PASS. (If this test compares the migrated schema to the ORM metadata and fails, reconcile any column type/nullability difference between the migration above and `WorkItemAttachmentRow` until it passes — they must match exactly.)

- [ ] **Step 7: Commit**

```bash
git add src/adapters/database/orm.py src/adapters/database/repositories.py src/adapters/database/uow.py migrations/versions/attach01_work_item_attachments.py tests/unit/test_attachment_repository.py
git commit -m "feat: work_item_attachments table, repository, migration"
```

---

## Task 4: API — upload / list / download / delete

**Files:**
- Modify: `src/interactors/api/settings.py`, `src/interactors/api/deps.py`, `src/interactors/api/app.py`
- Create: `src/interactors/api/routes/attachments.py`
- Test: `tests/integration/test_attachments_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_attachments_api.py
"""Integration tests for work-item attachments."""
from fastapi.testclient import TestClient

from interactors.api.app import create_app
from interactors.api.settings import Settings


def _client(**overrides):
    return TestClient(
        create_app(Settings(_env_file=None, database_url="sqlite:///:memory:", **overrides))
    )


def _project(c) -> str:
    return c.post("/projects", json={"name": "A", "repo_url": "r"}).json()["data"]["id"]


def _epic(c, pid) -> str:
    return c.post(
        f"/projects/{pid}/work-items", json={"kind": "epic", "title": "E"}
    ).json()["data"]["id"]


PNG = b"\x89PNG\r\n\x1a\n\x00\x00"


def test_upload_list_download_delete():
    c = _client()
    pid = _project(c)
    wi = _epic(c, pid)

    up = c.post(
        f"/work-items/{wi}/attachments",
        files={"file": ("shot.png", PNG, "image/png")},
    )
    assert up.status_code == 200, up.text
    att = up.json()["data"]
    assert att["filename"] == "shot.png" and att["content_type"] == "image/png"
    assert att["origin"] == "human" and att["size_bytes"] == len(PNG)

    listing = c.get(f"/work-items/{wi}/attachments").json()["data"]
    assert [a["id"] for a in listing] == [att["id"]]

    dl = c.get(f"/attachments/{att['id']}")
    assert dl.status_code == 200
    assert dl.content == PNG
    assert dl.headers["content-type"].startswith("image/png")
    assert dl.headers["content-disposition"].startswith("inline")
    assert dl.headers["x-content-type-options"] == "nosniff"

    assert c.delete(f"/attachments/{att['id']}").status_code == 200
    assert c.get(f"/attachments/{att['id']}").status_code == 404


def test_markdown_is_attachment_disposition():
    c = _client()
    pid = _project(c)
    wi = _epic(c, pid)
    up = c.post(
        f"/work-items/{wi}/attachments",
        files={"file": ("notes.md", b"# hi", "text/markdown")},
    )
    att = up.json()["data"]
    dl = c.get(f"/attachments/{att['id']}")
    assert dl.headers["content-disposition"].startswith("attachment")


def test_rejects_disallowed_type():
    c = _client()
    pid = _project(c)
    wi = _epic(c, pid)
    r = c.post(f"/work-items/{wi}/attachments", files={"file": ("x.svg", b"<svg/>", "image/svg+xml")})
    assert r.status_code == 415


def test_rejects_oversized():
    c = _client(max_attachment_bytes=8)
    pid = _project(c)
    wi = _epic(c, pid)
    r = c.post(f"/work-items/{wi}/attachments", files={"file": ("big.png", b"123456789", "image/png")})
    assert r.status_code == 413


def test_unknown_work_item_404():
    c = _client()
    r = c.post("/work-items/nope/attachments", files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_attachments_api.py -v`
Expected: FAIL — 404 on upload (route not registered), or a `python-multipart` error (handled in Step 4).

- [ ] **Step 3: Add settings**

In `src/interactors/api/settings.py`, add these fields to `Settings` (after `task_queue`):

```python
    storage_dir: str = "data"
    max_attachment_bytes: int = 10 * 1024 * 1024
```

- [ ] **Step 4: Add the `storage` dependency**

In `src/interactors/api/deps.py`, add:

```python
def storage(request: Request):
    from adapters.storage.local import LocalStorageAdapter

    return LocalStorageAdapter(base_dir=request.app.state.settings.storage_dir)
```

- [ ] **Step 5: Create `src/interactors/api/routes/attachments.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import Response

from adapters.database.ports import UnitOfWork
from adapters.storage.ports import StoragePort
from domain.attachments import (
    ALLOWED_ATTACHMENT_TYPES,
    attachment_storage_key,
    canonical_extension,
    is_inline_image,
    sanitize_filename,
)
from domain.errors import RecordNotFound
from domain.models import WorkItemAttachment
from interactors.api.deps import get_uow, storage
from interactors.api.envelope import ok

router = APIRouter(tags=["attachments"])


@router.post("/work-items/{item_id}/attachments")
async def upload(
    item_id: str,
    file: UploadFile,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    store: StoragePort = Depends(storage),
) -> dict:
    max_bytes = request.app.state.settings.max_attachment_bytes
    ext = canonical_extension(file.filename or "")
    if ext is None:
        raise HTTPException(status_code=415, detail="unsupported attachment type")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty file")
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail="attachment too large")

    with uow.transaction():
        item = uow.work_items.get(item_id)  # owner-scoped; RecordNotFound -> 404
        attachment = WorkItemAttachment(
            owner_id=item.owner_id,
            work_item_id=item_id,
            filename=sanitize_filename(file.filename or "file"),
            content_type=ALLOWED_ATTACHMENT_TYPES[ext],
            size_bytes=len(content),
            storage_key="",  # set below once we have the id
        )
        attachment = attachment.model_copy(
            update={"storage_key": attachment_storage_key(item_id, attachment.id, ext)}
        )
        store.write_bytes(attachment.storage_key, content)
        created = uow.work_item_attachments.create(attachment)
    return ok(created.model_dump(mode="json"))


@router.get("/work-items/{item_id}/attachments")
def list_for_item(item_id: str, uow: UnitOfWork = Depends(get_uow)) -> dict:
    with uow.transaction():
        page = uow.work_item_attachments.list(
            filters={"work_item_id": item_id}, page_size=200, order_by="created_at"
        )
    return ok([a.model_dump(mode="json") for a in page.results])


@router.get("/attachments/{attachment_id}")
def download(
    attachment_id: str,
    uow: UnitOfWork = Depends(get_uow),
    store: StoragePort = Depends(storage),
) -> Response:
    with uow.transaction():
        att = uow.work_item_attachments.get(attachment_id)  # owner-scoped -> 404
    if not store.exists(att.storage_key):
        raise RecordNotFound("attachment blob missing")
    disposition = "inline" if is_inline_image(att.content_type) else "attachment"
    return Response(
        content=store.read_bytes(att.storage_key),
        media_type=att.content_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{att.filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/attachments/{attachment_id}")
def delete(
    attachment_id: str,
    uow: UnitOfWork = Depends(get_uow),
    store: StoragePort = Depends(storage),
) -> dict:
    with uow.transaction():
        att = uow.work_item_attachments.get(attachment_id)  # owner-scoped -> 404
        store.delete(att.storage_key)  # idempotent: missing blob is a no-op
        uow.work_item_attachments.delete(attachment_id)
    return ok({"deleted": attachment_id})
```

- [ ] **Step 6: Register the router in `src/interactors/api/app.py`**

Add `attachments` to the `from interactors.api.routes import (...)` block, and add this line next to the other `app.include_router(...)` calls (after `app.include_router(epics.router)`):

```python
    app.include_router(attachments.router)
```

- [ ] **Step 7: Run tests; install `python-multipart` if needed**

Run: `uv run pytest tests/integration/test_attachments_api.py -v`

If it fails with `RuntimeError: Form data requires "python-multipart" to be installed`, run:

```bash
uv add python-multipart
```

Then re-run. Expected: PASS (5 passed).

- [ ] **Step 8: Commit**

```bash
git add src/interactors/api/settings.py src/interactors/api/deps.py src/interactors/api/routes/attachments.py src/interactors/api/app.py tests/integration/test_attachments_api.py pyproject.toml uv.lock
git commit -m "feat: work-item attachment upload/list/download/delete API"
```

(If `uv add` was not needed, drop `pyproject.toml uv.lock` from the `git add`.)

---

## Task 5: Backend gate

- [ ] **Step 1: Coverage + lint**

Run: `make coverage`
Expected: all pass; coverage ≥ 80%.

Run: `make lint`
Expected: clean. (Fix any line-length/import-order issues in the files this feature touched and re-run.)

(No commit — gate only.)

---

## Task 6: UI API client — multipart helper + attachments client

**Files:**
- Modify: `ui/src/lib/api/client.ts`
- Create: `ui/src/lib/api/attachments.ts`

- [ ] **Step 1: Add `apiPostForm` to `ui/src/lib/api/client.ts`**

Add this exported function (after `apiPost`). It must NOT set a `Content-Type` header (the browser sets the multipart boundary), and it reuses the same envelope handling:

```typescript
export async function apiPostForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(BASE + path, { method: "POST", body: form });
  let body: Envelope<T>;
  try {
    body = (await res.json()) as Envelope<T>;
  } catch {
    throw new ApiError(res.status, res.statusText || "request failed");
  }
  if (!res.ok || !body.success) {
    throw new ApiError(res.status, body.error ?? res.statusText);
  }
  return body.data as T;
}
```

- [ ] **Step 2: Create `ui/src/lib/api/attachments.ts`**

```typescript
import { BASE, apiDelete, apiGet, apiPostForm } from "./client";

export interface WorkItemAttachment {
  id: string;
  work_item_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  origin: string;
  created_at: string;
}

export const attachmentKeys = {
  forItem: (itemId: string) => ["attachments", itemId] as const,
};

export function attachmentUrl(attachmentId: string): string {
  return `${BASE}/attachments/${attachmentId}`;
}

export function isImage(att: WorkItemAttachment): boolean {
  return att.content_type.startsWith("image/");
}

export async function getAttachments(itemId: string): Promise<WorkItemAttachment[]> {
  return apiGet<WorkItemAttachment[]>(`/work-items/${itemId}/attachments`);
}

export async function uploadAttachment(itemId: string, file: File): Promise<WorkItemAttachment> {
  const form = new FormData();
  form.append("file", file);
  return apiPostForm<WorkItemAttachment>(`/work-items/${itemId}/attachments`, form);
}

export async function deleteAttachment(attachmentId: string): Promise<void> {
  await apiDelete(`/attachments/${attachmentId}`);
}
```

- [ ] **Step 3: Export `BASE` from `ui/src/lib/api/client.ts`**

`attachments.ts` imports `BASE`. In `client.ts` the first line is `const BASE = ...`. Change it to export it:

```typescript
export const BASE = import.meta.env.VITE_API_BASE_URL || "/api";
```

- [ ] **Step 4: Verify it compiles**

Run: `cd ui && pnpm lint`
Expected: clean (eslint + tsc).

- [ ] **Step 5: Commit**

```bash
git add ui/src/lib/api/client.ts ui/src/lib/api/attachments.ts
git commit -m "feat: UI attachments API client + multipart helper"
```

---

## Task 7: UI — Attachments section in the ticket panel

**Files:**
- Create: `ui/src/modules/work-items/useAttachments.ts`, `ui/src/modules/work-items/Attachments.tsx`
- Modify: `ui/src/modules/work-items/TicketPanel.tsx`
- Test: `ui/src/modules/work-items/Attachments.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// ui/src/modules/work-items/Attachments.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "@/test/server";
import { Attachments } from "./Attachments";

function renderAttachments() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Attachments itemId="wi1" />
    </QueryClientProvider>,
  );
}

const list = [
  { id: "a1", work_item_id: "wi1", filename: "shot.png", content_type: "image/png", size_bytes: 12, origin: "human", created_at: "" },
  { id: "a2", work_item_id: "wi1", filename: "notes.md", content_type: "text/markdown", size_bytes: 40, origin: "human", created_at: "" },
];

test("renders an image thumbnail and a download link", async () => {
  server.use(
    http.get("/api/work-items/wi1/attachments", () =>
      HttpResponse.json({ success: true, error: null, data: list })),
  );
  renderAttachments();
  await waitFor(() => expect(screen.getByRole("img", { name: /shot.png/i })).toBeInTheDocument());
  expect(screen.getByRole("img", { name: /shot.png/i })).toHaveAttribute("src", "/api/attachments/a1");
  expect(screen.getByRole("link", { name: /notes.md/i })).toHaveAttribute("href", "/api/attachments/a2");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && pnpm vitest run src/modules/work-items/Attachments.test.tsx`
Expected: FAIL — cannot resolve `./Attachments`.

- [ ] **Step 3: Create `ui/src/modules/work-items/useAttachments.ts`**

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  attachmentKeys,
  deleteAttachment,
  getAttachments,
  uploadAttachment,
} from "@/lib/api/attachments";

export function useAttachments(itemId: string) {
  const qc = useQueryClient();
  const list = useQuery({
    queryKey: attachmentKeys.forItem(itemId),
    queryFn: () => getAttachments(itemId),
  });
  const invalidate = () =>
    qc.invalidateQueries({ queryKey: attachmentKeys.forItem(itemId) });

  const upload = useMutation({
    mutationFn: (file: File) => uploadAttachment(itemId, file),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: (attachmentId: string) => deleteAttachment(attachmentId),
    onSuccess: invalidate,
  });
  return { list, upload, remove };
}
```

- [ ] **Step 4: Create `ui/src/modules/work-items/Attachments.tsx`**

```tsx
import { type ChangeEvent } from "react";
import { Button } from "@/components/ui/Button";
import { attachmentUrl, isImage } from "@/lib/api/attachments";
import { useAttachments } from "./useAttachments";

export function Attachments({ itemId }: { itemId: string }) {
  const { list, upload, remove } = useAttachments(itemId);

  const onPick = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) upload.mutate(file);
    e.target.value = "";
  };

  return (
    <div>
      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-subtle">Attachments</h3>
      <ul className="mb-2 space-y-2">
        {(list.data ?? []).map((att) => (
          <li key={att.id} className="flex items-center gap-2">
            {isImage(att) ? (
              <a href={attachmentUrl(att.id)} target="_blank" rel="noreferrer">
                <img src={attachmentUrl(att.id)} alt={att.filename} className="h-12 w-12 rounded border border-line object-cover" />
              </a>
            ) : (
              <a className="text-sm text-accent hover:underline" href={attachmentUrl(att.id)} target="_blank" rel="noreferrer">
                {att.filename} ({att.size_bytes} B)
              </a>
            )}
            <Button variant="ghost" size="sm" onClick={() => remove.mutate(att.id)}>Delete</Button>
          </li>
        ))}
      </ul>
      <input type="file" aria-label="Upload attachment" onChange={onPick} className="text-xs text-subtle" />
      {upload.isError && <p className="text-sm text-danger">{(upload.error as Error).message}</p>}
    </div>
  );
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd ui && pnpm vitest run src/modules/work-items/Attachments.test.tsx`
Expected: PASS.

- [ ] **Step 6: Mount the section in `TicketPanel.tsx`**

In `ui/src/modules/work-items/TicketPanel.tsx`, add the import near the other imports:

```typescript
import { Attachments } from "./Attachments";
```

Then render it inside the `data &&` block, immediately after the acceptance-criteria `<div>` and before the `update.isError` line:

```tsx
          <Attachments itemId={itemId} />
```

- [ ] **Step 7: Verify lint + the panel test still passes**

Run: `cd ui && pnpm lint && pnpm vitest run src/modules/work-items/TicketPanel.test.tsx src/modules/work-items/Attachments.test.tsx`
Expected: lint clean; tests pass. (If `TicketPanel.test.tsx` lacks an msw handler for `GET /api/work-items/:id/attachments` and errors on the new fetch, add a handler returning `{ success: true, error: null, data: [] }` for that path in the test's `server.use(...)` setup.)

- [ ] **Step 8: Commit**

```bash
git add ui/src/modules/work-items/useAttachments.ts ui/src/modules/work-items/Attachments.tsx ui/src/modules/work-items/TicketPanel.tsx ui/src/modules/work-items/TicketPanel.test.tsx ui/src/modules/work-items/Attachments.test.tsx
git commit -m "feat: attachments section in the ticket panel"
```

---

## Task 8: UI gate

- [ ] **Step 1: Lint + full test suite + build**

Run: `cd ui && pnpm lint`
Expected: clean.

Run: `cd ui && pnpm vitest run`
Expected: all pass.

Run: `cd ui && pnpm build`
Expected: build succeeds. After it, remove the build artifact so it doesn't shadow API routes in any later backend run: `rm -rf ui/dist`.

(No commit — gate only.)

---

## Task 9: PR

- [ ] **Step 1: Final gates green**

Run: `make coverage && make lint && (cd ui && pnpm lint && pnpm vitest run)`
Expected: all green.

- [ ] **Step 2: Push and open the PR**

```bash
git push -u origin feat/work-item-attachments
gh pr create --title "feat: work-item attachments (upload, preview, download)" \
  --body "Implements docs/specs/2026-06-16-work-item-attachments-design.md: upload files (images, .md, .txt) to any work item, preview images inline + download others, owner-scoped via an authed route. New work_item_attachments table + migration; blobs in the existing StoragePort; origin field reserved for a later agent-artifacts cycle. Test plan: make coverage + make lint green; UI pnpm lint + vitest + build green."
```

---

## Self-Review Notes

- **Spec coverage:** data model + storage (Tasks 1-3); upload/list/download/delete + validation/security headers + settings (Task 4); UI client + multipart (Task 6); ticket-panel section with image preview + download (Task 7). SVG excluded and inline-vs-attachment disposition are exercised in Task 4 tests.
- **Allowlist source:** kept as the `ALLOWED_ATTACHMENT_TYPES` domain constant (pure, testable). Max size is the settings knob (`max_attachment_bytes`); the spec's "settings-configurable allowlist" is simplified to a domain constant — note for the spec if you want it env-driven later.
- **Type consistency:** `WorkItemAttachment` fields match across `models.py`, `orm.py`, the migration, and the TS `WorkItemAttachment`; `attachment_storage_key`/`canonical_extension`/`is_inline_image`/`sanitize_filename` signatures are used identically in Task 4; `apiPostForm`/`attachmentUrl`/`isImage` match between `attachments.ts` and `Attachments.tsx`.
- **Stored content-type is canonical** (from the allowlist), never the browser-declared type — closes the content-type-spoofing/XSS angle on download.
