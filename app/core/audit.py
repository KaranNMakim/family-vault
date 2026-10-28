"""Append-only, hash-chained audit log stored in the vault.

Each entry stores sha256(prev_hash + canonical JSON body). Editing or deleting any row breaks
the chain, which `verify` detects. Details are redacted before they are written.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from app.logs import redact

GENESIS = "0" * 64


def _hash(prev: str, body: str) -> str:
    return hashlib.sha256((prev + body).encode()).hexdigest()


def append(store, actor: str, role: str, action: str, target: str = "", details: dict | None = None,
           ts: datetime | None = None) -> dict:
    row = store.db.execute("SELECT seq, hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
    seq, prev = (row[0] + 1, row[1]) if row else (1, GENESIS)
    entry = {"seq": seq, "ts": (ts or datetime.now(UTC)).isoformat(timespec="seconds"), "actor": actor,
             "role": role, "action": action, "target": target, "details": redact(details or {})}
    body = json.dumps(entry, sort_keys=True)
    h = _hash(prev, body)
    store.db.execute("INSERT INTO audit VALUES (?, ?, ?, ?)", (seq, body, prev, h))
    store.db.commit()
    return entry | {"hash": h}


def entries(store, limit: int = 200) -> list[dict]:
    rows = store.db.execute("SELECT body, hash FROM audit ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()
    return [json.loads(b) | {"hash": h} for b, h in rows]


def verify(store) -> tuple[bool, int | None]:
    """Return (ok, first bad seq)."""
    prev = GENESIS
    expected_seq = 1
    for seq, body, stored_prev, h in store.db.execute("SELECT seq, body, prev_hash, hash FROM audit ORDER BY seq"):
        if seq != expected_seq or stored_prev != prev or _hash(prev, body) != h or json.loads(body)["seq"] != seq:
            return False, seq
        prev, expected_seq = h, seq + 1
    return True, None
