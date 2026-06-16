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
