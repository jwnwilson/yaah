from typing import Any


def ok(data: Any, meta: dict | None = None) -> dict:
    body: dict = {"success": True, "data": data, "error": None}
    if meta:
        body["meta"] = meta
    return body


def err(message: str) -> dict:
    return {"success": False, "data": None, "error": message}
