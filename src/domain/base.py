"""Shared domain primitives: id and timestamp factories used by every entity model."""
from datetime import datetime, timezone
from uuid import uuid4


def new_id() -> str:
    return uuid4().hex


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
