"""Input guard: we only ever store MASKED identifiers (last 4 characters).

Full account / policy / folio numbers, government IDs (Aadhaar, PAN), passwords, PINs, OTPs
and card numbers are rejected with a plain-language explanation. The guard runs in the API
layer (and is mirrored in the web UI), so a client cannot bypass it.
"""

from __future__ import annotations

import re
from typing import Any

WHY = (
    "family-vault only needs the last 4 characters to help your family find the right account. "
    "Never store full account numbers, ID numbers, passwords, PINs or OTPs here."
)

# Keys that must never appear in any payload, whatever their value.
FORBIDDEN_KEYS = {
    "password", "passwd", "pin", "mpin", "upi_pin", "otp", "cvv", "cvc",
    "account_number", "full_account_number", "card_number", "policy_number", "folio_number",
    "aadhaar", "aadhar", "aadhaar_number", "pan", "pan_number", "passport", "passport_number",
    "voter_id", "driving_licence", "ssn",
}

_MASK_CHARS = "Xx*•#-_ "
_VISIBLE = re.compile(r"^[A-Za-z0-9]{1,4}$")
# Dates are allowed in free text; strip them before looking for long digit runs.
_DATES = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})\b")
_DIGIT_RUN = re.compile(r"(?:\d[ -]?){6,}")
_PAN = re.compile(r"\b[A-Za-z]{5}\d{4}[A-Za-z]\b")
_SECRET = re.compile(
    r"\b(password|passwd|pwd|pass ?code|m?pin|upi ?pin|otp|cvv|cvc|net ?banking (login|password))\b"
    r"(\s*(is|was|=|:|-)\s*\S+|\s+\S*\d\S*)",
    re.IGNORECASE,
)


class MaskingError(ValueError):
    """Raised when an input looks like a full identifier or secret."""

    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        super().__init__(f"{field}: {reason}. {WHY}")

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "reason": self.reason, "why": WHY}


def mask_identifier(value: str, field: str = "masked_id") -> str:
    """Validate and normalise a masked identifier to ``XXXX1234`` form.

    Accepts ``1234``, ``XXXX1234``, ``****1234``, ``xx-xx-1234``. Rejects anything that
    reveals more than 4 characters.
    """
    if not isinstance(value, str) or not value.strip():
        raise MaskingError(field, "enter only the last 4 characters")
    visible = value.strip().lstrip(_MASK_CHARS)
    visible = visible.replace(" ", "").replace("-", "")
    if not _VISIBLE.match(visible):
        digits = sum(c.isdigit() for c in value)
        if digits > 4 or len(visible) > 4:
            raise MaskingError(field, "this looks like a full number; enter only the last 4 characters")
        raise MaskingError(field, "use letters/digits only, at most 4 visible characters (e.g. XXXX1234)")
    return f"XXXX{visible.upper()}"


def check_free_text(value: str, field: str = "text") -> str:
    """Reject free text that appears to contain a full number, ID or secret."""
    if not isinstance(value, str):
        return value
    scrubbed = _DATES.sub(" ", value)
    if _SECRET.search(value):
        raise MaskingError(field, "this looks like a password, PIN or OTP — never store those")
    if _PAN.search(value):
        raise MaskingError(field, "this looks like a PAN number")
    if _DIGIT_RUN.search(scrubbed):
        raise MaskingError(field, "this contains a long number (account, card or ID number?)")
    return value


def reject_forbidden_keys(payload: Any, path: str = "") -> None:
    """Recursively reject payload keys that name a forbidden identifier or secret."""
    if isinstance(payload, dict):
        for k, v in payload.items():
            key = str(k).lower().replace("-", "_")
            if key in FORBIDDEN_KEYS:
                raise MaskingError(f"{path}{k}", "this field is not accepted")
            reject_forbidden_keys(v, f"{path}{k}.")
    elif isinstance(payload, list):
        for i, v in enumerate(payload):
            reject_forbidden_keys(v, f"{path}{i}.")
