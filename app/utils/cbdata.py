from __future__ import annotations

import base64
import uuid


__all__ = ["pack_uuid", "unpack_uuid", "parse_uuid"]


def pack_uuid(uuid_str: str) -> str:
    """Pack a UUID string into a URL-safe base64 string without padding."""
    uid = uuid.UUID(uuid_str)
    packed = base64.urlsafe_b64encode(uid.bytes).decode().rstrip("=")
    return packed


def _add_padding(packed: str) -> str:
    missing = len(packed) % 4
    if missing:
        packed += "=" * (4 - missing)
    return packed


def unpack_uuid(packed: str) -> str:
    padded = _add_padding(packed)
    raw = base64.urlsafe_b64decode(padded.encode())
    return str(uuid.UUID(bytes=raw))


def parse_uuid(value: str) -> str:
    """Return a canonical UUID string from either a UUID or packed form."""
    if "-" in value:
        try:
            return str(uuid.UUID(value))
        except ValueError:
            pass
    return unpack_uuid(value)
