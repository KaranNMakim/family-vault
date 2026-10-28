"""In-memory demo sessions and the registry of unlocked vaults.

The vault key lives only in server memory while a vault is unlocked. Authentication is SIMULATED:
whoever knows a family's demo passphrase gets an owner session and can "act as" other family roles
via the role switcher. Real per-member auth and key wrapping are productization items.
"""

from __future__ import annotations

import re
import secrets
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.core.access import Principal
from app.core.estate import Estate
from app.kg.store import NetworkXSQLiteStore


@dataclass
class Session:
    token: str
    family_id: str
    principal: Principal
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class Registry:
    def __init__(self, vault_dir: Path | None = None):
        self.vault_dir = vault_dir or get_settings().vault_dir
        self.stores: dict[str, NetworkXSQLiteStore] = {}
        self.sessions: dict[str, Session] = {}
        self.lock = threading.RLock()

    def path(self, family_id: str) -> Path:
        if not re.fullmatch(r"[a-z0-9_]{1,40}", family_id):
            raise KeyError(family_id)
        return self.vault_dir / f"{family_id}.db"

    def families(self) -> list[dict]:
        if not self.vault_dir.exists():
            return []
        return [NetworkXSQLiteStore.read_public_meta(p) | {"id": p.stem} for p in sorted(self.vault_dir.glob("*.db"))]

    def unlock(self, family_id: str, passphrase: str) -> NetworkXSQLiteStore:
        with self.lock:
            path = self.path(family_id)
            store = NetworkXSQLiteStore.open(path, passphrase)  # raises WrongPassphrase
            if family_id in self.stores:  # verified passphrase; reuse the shared instance
                store.close()
                return self.stores[family_id]
            self.stores[family_id] = store
            return store

    def create(self, display_name: str, passphrase: str) -> tuple[str, NetworkXSQLiteStore]:
        with self.lock:
            fid = f"family_{uuid.uuid4().hex[:6]}"
            store = NetworkXSQLiteStore.create(self.path(fid), passphrase,
                                               {"id": fid, "display_name": display_name, "synthetic": True})
            self.stores[fid] = store
            return fid, store

    def new_session(self, family_id: str, principal: Principal) -> Session:
        s = Session(secrets.token_urlsafe(24), family_id, principal)
        self.sessions[s.token] = s
        return s

    def get(self, token: str) -> Session:
        return self.sessions[token]

    def end(self, token: str) -> None:
        self.sessions.pop(token, None)

    def store(self, family_id: str) -> NetworkXSQLiteStore:
        return self.stores[family_id]

    def estate(self, family_id: str) -> Estate:
        return Estate(self.stores[family_id], get_settings().as_of)

    def close_all(self) -> None:
        for s in self.stores.values():
            s.close()
        self.stores.clear()
        self.sessions.clear()
