"""Time-based one-time passwords (RFC 6238: HMAC-SHA1, 30-second steps, 6 digits).

Compatible with Google Authenticator, Microsoft Authenticator, Authy and similar apps. The shared
secret is stored in the vault encrypted with the vault key, so it can only be read after the
passphrase step succeeds.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time
from urllib.parse import quote

STEP = 30
DIGITS = 6


def new_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    s = secret.strip().replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def code_at(secret: str, t: float | None = None) -> str:
    counter = int((time.time() if t is None else t) // STEP)
    digest = hmac.new(_key(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def verify(secret: str, code: str, t: float | None = None, window: int = 1, last_step: int | None = None) -> int | None:
    """Return the matched time step, or None. Rejects reuse of a step at or before `last_step`."""
    code = (code or "").strip().replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return None
    now = time.time() if t is None else t
    current = int(now // STEP)
    for step in range(current - window, current + window + 1):
        if last_step is not None and step <= last_step:
            continue
        if hmac.compare_digest(code_at(secret, step * STEP), code):
            return step
    return None


def provisioning_uri(secret: str, account: str, issuer: str = "family-vault demo") -> str:
    label = quote(f"{issuer}:{account}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits={DIGITS}&period={STEP}"
