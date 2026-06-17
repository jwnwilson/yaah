"""Unit tests for pure attachment policy."""
from domain.attachments import (
    ALLOWED_ATTACHMENT_TYPES,
    WorkItemAttachment,
    attachment_storage_key,
    canonical_extension,
    is_inline_image,
    sanitize_filename,
)


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
