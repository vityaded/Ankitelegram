from __future__ import annotations

import base64
import hmac
import hashlib
import time
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class UploadTokenData:
    admin_id: int
    exp: int

def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")

def _b64url_decode(s: str) -> bytes:
    pad = "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode(s + pad)

def make_upload_token(secret: str, admin_id: int, ttl_seconds: int = 3600) -> str:
    exp = int(time.time()) + int(ttl_seconds)
    payload = f"{admin_id}:{exp}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()[:24]
    raw = payload + b":" + sig.encode("ascii")
    return _b64url_encode(raw)

def verify_upload_token(secret: str, token: str) -> Optional[UploadTokenData]:
    try:
        raw = _b64url_decode(token)
        parts = raw.decode("utf-8").split(":")
        if len(parts) != 3:
            return None
        admin_id = int(parts[0])
        exp = int(parts[1])
        sig = parts[2]
        if exp < int(time.time()):
            return None
        payload = f"{admin_id}:{exp}".encode("utf-8")
        expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()[:24]
        if not hmac.compare_digest(sig, expected):
            return None
        return UploadTokenData(admin_id=admin_id, exp=exp)
    except Exception:
        return None
