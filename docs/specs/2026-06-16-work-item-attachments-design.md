# Work-Item Attachments — Design

> Status: design (approved 2026-06-16). Advances gap #4 in
> [project-history.md](../project-history.md): "no ticket attachments/artifacts (.md, images)".
>
> **Foundation cycle.** This builds human-uploaded attachments on work items. A later spec
> surfaces **agent-produced run artifacts** on tickets, reusing this model's `origin` field.

## Goal

Let a person attach files (screenshots, notes, spec docs) to any work item (epic/feature/task)
from the ticket panel, then view and download them. Images preview inline; other files are
download links. The data model carries an `origin` field so a future cycle can add
`origin="agent"` artifacts without a migration.

## Decisions

- **All three work-item kinds** can carry attachments (uniform).
- **Storage:** metadata row in a new DB table + blob in the existing `StoragePort`
  (`LocalStorageAdapter`); downloads go through an **authed, owner-scoped route** — not a static
  mount. Rejected alternatives: bytes in a DB `LargeBinary` column (DB bloat, wrong for images);
  static-file mount over the storage dir (bypasses auth/owner-scoping).
- **Viewing:** raster images render as inline thumbnails (click → full size); `.md`/other files
  are named, sized download links. No markdown-rendering dependency added.
- **Allowlist:** `png, jpeg/jpg, gif, webp, md, txt`. **SVG and HTML are excluded** — inline-served
  SVG/HTML is an XSS vector. Max size default **10 MB** (settings-configurable).
- The deferred **per-task-card feature tag** is unrelated and ships as its own small PR, not here.

## Architecture

Hexagonal: pure validation/key-builder logic in `domain/`, blob I/O via the storage port,
metadata via a repository, HTTP wiring in `interactors/`. No business logic in routes.

### Data model

New table **`work_item_attachments`**:

| column | type | notes |
|---|---|---|
| `id` | str(32) PK | uuid hex |
| `owner_id` | str(64) indexed | owner scoping |
| `work_item_id` | str(32) indexed | parent ticket |
| `filename` | str(300) | sanitized original name, for display + download |
| `content_type` | str(100) | validated MIME |
| `size_bytes` | int | |
| `storage_key` | str(400) | `attachments/{work_item_id}/{attachment_id}{ext}` |
| `origin` | str(16) | `"human"` now; `"agent"` reserved |
| `created_at` | datetime(tz) | |

Domain model `WorkItemAttachment` (Pydantic, immutable via `model_copy`). A
`WorkItemAttachmentRepository` registered on the UnitOfWork (follows the
notifications/messages repository pattern). An **Alembic migration** adds the table.

### Storage

Reuse `StoragePort` / `LocalStorageAdapter`. Add **`read_bytes(key) -> bytes`** to the port and
local impl (it currently exposes only `read_text`). The blob key is built from the generated
**attachment id and a validated extension — never the raw filename** (prevents path traversal and
collisions); the original filename is kept in the DB only for display/download.

### API — `interactors/api/routes/attachments.py`

- **`POST /work-items/{item_id}/attachments`** — multipart `UploadFile`. Validates: work item
  exists + owned (404); content type/extension in the allowlist (415); size ≤ max (413); non-empty
  (400). Sanitizes the filename for display. Writes the blob via storage, creates the metadata row,
  returns the attachment metadata (incl. its download path).
- **`GET /work-items/{item_id}/attachments`** — owner-scoped list of metadata for the ticket.
- **`GET /attachments/{attachment_id}`** — owner-scoped download. Reads bytes from storage, returns
  them with the stored `content_type`. **Raster images** → `Content-Disposition: inline` (so `<img>`
  works); everything else → `attachment` (forced download). `X-Content-Type-Options: nosniff` always.
- **`DELETE /attachments/{attachment_id}`** — owner-scoped; deletes the blob then the row.

Routes are registered in `app.py`. Owner scoping comes from the UoW required filter, so cross-tenant
access returns 404.

### UI — board / work-items module

- `lib/api/client.ts` gains **`apiPostForm`** (multipart; sets no `Content-Type`, so the browser
  adds the boundary; still unwraps the `{success,data,error}` envelope and throws `ApiError`).
- `lib/api/attachments.ts`: `WorkItemAttachment` type, `attachmentKeys`, `getAttachments(itemId)`,
  `uploadAttachment(itemId, file)`, `deleteAttachment(id)`, and `attachmentUrl(id)`
  (`${BASE}/attachments/${id}`).
- `TicketPanel.tsx` gains an **Attachments** section: an upload control + a list. Images render as
  inline `<img>` thumbnails linking to full size; other files show a `filename (size)` download
  link. Each row has a delete button. Backed by a `useAttachments(itemId)` query and
  upload/delete mutations that invalidate it.

### Settings

`max_attachment_bytes: int = 10 * 1024 * 1024` and an allowed-type map (extension ↔ MIME) on
`Settings` (env prefix `YAAH_`).

## Validation & security

- Allowlist enforced by both extension and MIME; mismatch or disallowed → 415.
- SVG/HTML excluded; raster images are safe to serve inline.
- Size cap → 413; empty upload → 400.
- Storage key never contains user input beyond a validated extension → no path traversal.
- Download route owner-scoped → cross-tenant → 404.
- `X-Content-Type-Options: nosniff` on downloads; non-images forced to `attachment` disposition.

## Error handling

Unknown/zero-owned work item or attachment → 404. Oversized → 413. Disallowed type → 415. Empty
file → 400. All via the `{success,data,error}` envelope. Blob-delete is best-effort-then-row:
if the blob is already gone, the row delete still succeeds (idempotent delete).

## Testing (TDD, 80% gate)

**Unit (pure domain)**
- `sanitize_filename`: strips path separators/control chars; preserves a readable name.
- `validate_attachment(filename, content_type, size, *, max_bytes)`: accepts allowlisted types;
  rejects disallowed type, size over cap, empty.
- `attachment_storage_key(work_item_id, attachment_id, ext)`: deterministic, no raw filename.

**Integration (API)**
- Upload happy-path returns metadata; the blob is retrievable.
- List returns the ticket's attachments (owner-scoped).
- Download returns correct bytes, `Content-Type`, and disposition (`inline` for png, `attachment`
  for md) + `nosniff`.
- Delete removes the row and the blob; second download → 404.
- Reject oversized → 413; disallowed type (e.g. `.exe`/`svg`) → 415; unknown work item → 404;
  cross-tenant attachment id → 404.

**UI (vitest)**
- Attachments section renders a list including an image thumbnail (`<img>` with the download URL)
  and a download link for a `.md`.
- Choosing a file calls `uploadAttachment` (asserts `apiPostForm` hit with `FormData`).
- Delete calls the API and invalidates the query.

## Build order

1. Domain: `WorkItemAttachment` + pure `sanitize_filename` / `validate_attachment` /
   `attachment_storage_key` (+ unit tests).
2. Storage: add `read_bytes` to port + local adapter (+ test).
3. Persistence: ORM row, repository, UoW registration, Alembic migration (+ repository test).
4. API: `attachments.py` routes + registration + settings (+ integration tests).
5. UI: `apiPostForm` + `attachments.ts` client.
6. UI: `TicketPanel` attachments section + `useAttachments` (+ vitest).

## Out of scope (YAGNI)

- Agent-produced run artifacts on tickets (next cycle — reuses `origin="agent"`).
- Markdown/PDF inline rendering (download only).
- S3 storage backend (the port is ready; local adapter is enough now).
- Attachment versioning, renaming, drag-and-drop reordering, thumbnails generation/resizing.
- The per-task-card feature tag (separate small PR).
