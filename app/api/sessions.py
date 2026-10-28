"""In-memory demo sessions, two-step unlock and the registry of unlocked vaults.

Unlock is two steps: (1) the vault passphrase derives the key (Argon2id) and opens the vault;
(2) a TOTP code from the family's authenticator app is checked against the secret stored encrypted
inside the vault. Only then is a session token issued. Failed passphrases are rate-limited per vault,
codes cannot be replayed, and sessions expire after inactivity.

The vault key lives only in server memory while a vault is unlocked. Per-person identities are still
SIMULATED: once the owner is verified, the demo role switcher can preview other family roles.
"""

from __future__ import annotations

import re
import secrets
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.config import get_settings
from app.core import totp
from app.core.access import Principal
from app.core.estate import Estate
from app.kg.store import NetworkXSQLiteStore

IDLE_TIMEOUT = timedelta(minutes=15)
ABSOLUTE_TIMEOUT = timedelta(hours=8)
CHALLENGE_TTL = timedelta(minutes=5)
MAX_CODE_ATTEMPTS = 5
MAX_PASSPHRASE_FAILURES = 5
FAILURE_WINDOW = timedelta(minutes=15)
LOCKOUT = timedelta(minutes=5)


def _now() -> datetime:
    return datetime.now(UTC)


class TooManyAttempts(Exception):
    def __init__(self, retry_after: timedelta):
        self.retry_after = retry_after
        super().__init__(f"too many attempts; try again in {max(1, int(retry_after.total_seconds() // 60) + 1)} min")


class ChallengeError(Exception):
    pass


@dataclass
class Session:
    token: str
    family_id: str
    principal: Principal
    created_at: datetime = field(default_factory=_now)
    last_seen: datetime = field(default_factory=_now)
    two_factor: bool = True


@dataclass
class Challenge:
    id: str
    family_id: str
    created_at: datetime = field(default_factory=_now)
    attempts: int = 0
    enroll: bool = False


class Registry:
    def __init__(self, vault_dir: Path | None = None):
        self.vault_dir = vault_dir or get_settings().vault_dir
        self.stores: dict[str, NetworkXSQLiteStore] = {}
        self.sessions: dict[str, Session] = {}
        self.challenges: dict[str, Challenge] = {}
        self.failures: dict[str, list[datetime]] = {}
        self.locked_until: dict[str, datetime] = {}
        self.last_step: dict[str, int] = {}
        self.lock = threading.RLock()

    def path(self, family_id: str) -> Path:
        if not re.fullmatch(r"[a-z0-9_]{1,40}", family_id):
            raise KeyError(family_id)
        return self.vault_dir / f"{family_id}.db"

    def families(self) -> list[dict]:
        if not self.vault_dir.exists():
            return []
        return [NetworkXSQLiteStore.read_public_meta(p) | {"id": p.stem} for p in sorted(self.vault_dir.glob("*.db"))]

    # ------------------------------------------------------------------ step 1: passphrase
    def check_lockout(self, family_id: str) -> None:
        until = self.locked_until.get(family_id)
        if until and _now() < until:
            raise TooManyAttempts(until - _now())

    def record_failure(self, family_id: str) -> int:
        """Record a failed passphrase; returns attempts left before lockout."""
        with self.lock:
            now = _now()
            recent = [t for t in self.failures.get(family_id, []) if now - t < FAILURE_WINDOW] + [now]
            self.failures[family_id] = recent
            if len(recent) >= MAX_PASSPHRASE_FAILURES:
                self.locked_until[family_id] = now + LOCKOUT
                self.failures[family_id] = []
                return 0
            return MAX_PASSPHRASE_FAILURES - len(recent)

    def unlock(self, family_id: str, passphrase: str) -> NetworkXSQLiteStore:
        with self.lock:
            self.check_lockout(family_id)
            path = self.path(family_id)
            store = NetworkXSQLiteStore.open(path, passphrase)  # raises WrongPassphrase
            self.failures.pop(family_id, None)
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

    # ------------------------------------------------------------------ step 2: one-time code
    def new_challenge(self, family_id: str, enroll: bool = False) -> Challenge:
        c = Challenge(secrets.token_urlsafe(18), family_id, enroll=enroll)
        self.challenges[c.id] = c
        return c

    def verify_challenge(self, challenge_id: str, code: str) -> Challenge:
        with self.lock:
            c = self.challenges.get(challenge_id)
            if not c or _now() - c.created_at > CHALLENGE_TTL:
                self.challenges.pop(challenge_id, None)
                raise ChallengeError("the verification step expired; please enter the passphrase again")
            c.attempts += 1
            if c.attempts > MAX_CODE_ATTEMPTS:
                self.challenges.pop(challenge_id, None)
                self.locked_until[c.family_id] = _now() + LOCKOUT
                raise TooManyAttempts(LOCKOUT)
            secret = self.stores[c.family_id].totp_secret()
            step = totp.verify(secret or "", code, last_step=self.last_step.get(c.family_id))
            if step is None:
                left = MAX_CODE_ATTEMPTS - c.attempts
                raise ChallengeError(f"that code is not right (or was already used); {left} attempt(s) left")
            self.last_step[c.family_id] = step
            del self.challenges[challenge_id]
            return c

    # ------------------------------------------------------------------ sessions
    def new_session(self, family_id: str, principal: Principal, two_factor: bool = True) -> Session:
        s = Session(secrets.token_urlsafe(24), family_id, principal, two_factor=two_factor)
        self.sessions[s.token] = s
        return s

    def get(self, token: str) -> Session:
        s = self.sessions[token]
        now = _now()
        if now - s.last_seen > IDLE_TIMEOUT or now - s.created_at > ABSOLUTE_TIMEOUT:
            self.sessions.pop(token, None)
            raise KeyError(token)
        s.last_seen = now
        return s

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
        self.challenges.clear()
