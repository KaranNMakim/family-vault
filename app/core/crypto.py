"""Field-level and blob encryption (PyNaCl / libsodium).

* KDF: Argon2id(passphrase, 16-byte random salt). The derived key is NEVER stored; only the
  salt, KDF parameters and a key-check ciphertext are persisted.
* Cipher: XChaCha20-Poly1305 (IETF AEAD) with a random 24-byte nonce per value. The associated
  data binds each ciphertext to its record and field (``node:<id>:<field>``), so ciphertexts
  cannot be swapped between fields or records without detection.
* Losing the passphrase means the data is unrecoverable — by design (see docs/security.md).
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass

import nacl.exceptions
import nacl.pwhash
from nacl.bindings import (
    crypto_aead_xchacha20poly1305_ietf_decrypt as _aead_decrypt,
)
from nacl.bindings import (
    crypto_aead_xchacha20poly1305_ietf_encrypt as _aead_encrypt,
)

NONCE_BYTES = 24
KEY_BYTES = 32
SALT_BYTES = nacl.pwhash.argon2id.SALTBYTES
PREFIX = "fv1:"
KEY_CHECK_PLAINTEXT = b"family-vault key check v1"
EXPORT_MAGIC = "family-vault-export"


class CryptoError(Exception):
    """Base error."""


class WrongPassphrase(CryptoError):
    pass


class TamperDetected(CryptoError):
    pass


@dataclass(frozen=True)
class KdfParams:
    salt: bytes
    opslimit: int = nacl.pwhash.argon2id.OPSLIMIT_INTERACTIVE
    memlimit: int = nacl.pwhash.argon2id.MEMLIMIT_INTERACTIVE

    @classmethod
    def new(cls) -> KdfParams:
        return cls(salt=os.urandom(SALT_BYTES))

    def to_dict(self) -> dict:
        return {
            "alg": "argon2id",
            "salt": base64.b64encode(self.salt).decode(),
            "opslimit": self.opslimit,
            "memlimit": self.memlimit,
        }

    @classmethod
    def from_dict(cls, d: dict) -> KdfParams:
        if d.get("alg") != "argon2id":
            raise CryptoError("unsupported KDF")
        return cls(salt=base64.b64decode(d["salt"]), opslimit=int(d["opslimit"]), memlimit=int(d["memlimit"]))


def derive_key(passphrase: str, params: KdfParams) -> bytes:
    if not passphrase or len(passphrase) < 8:
        raise CryptoError("passphrase must be at least 8 characters")
    return nacl.pwhash.argon2id.kdf(
        KEY_BYTES, passphrase.encode("utf-8"), params.salt, opslimit=params.opslimit, memlimit=params.memlimit
    )


def _seal(key: bytes, plaintext: bytes, aad: bytes) -> bytes:
    nonce = os.urandom(NONCE_BYTES)
    return nonce + _aead_encrypt(plaintext, aad, nonce, key)


def _open(key: bytes, blob: bytes, aad: bytes) -> bytes:
    if len(blob) < NONCE_BYTES + 16:
        raise TamperDetected("ciphertext truncated")
    try:
        return _aead_decrypt(blob[NONCE_BYTES:], aad, blob[:NONCE_BYTES], key)
    except nacl.exceptions.CryptoError as e:
        raise TamperDetected("authentication failed (wrong key or modified data)") from e


class VaultCipher:
    """Holds the derived key in memory for an unlocked vault session."""

    def __init__(self, key: bytes):
        if len(key) != KEY_BYTES:
            raise CryptoError("bad key length")
        self._key = key

    @classmethod
    def create(cls, passphrase: str) -> tuple[VaultCipher, KdfParams, str]:
        """New vault: returns cipher, KDF params and the key-check token to persist."""
        params = KdfParams.new()
        cipher = cls(derive_key(passphrase, params))
        return cipher, params, cipher.encrypt_bytes(KEY_CHECK_PLAINTEXT, b"keycheck")

    @classmethod
    def unlock(cls, passphrase: str, params: KdfParams, key_check: str) -> VaultCipher:
        cipher = cls(derive_key(passphrase, params))
        try:
            ok = cipher.decrypt_bytes(key_check, b"keycheck") == KEY_CHECK_PLAINTEXT
        except TamperDetected as e:
            raise WrongPassphrase("wrong passphrase") from e
        if not ok:
            raise WrongPassphrase("wrong passphrase")
        return cipher

    def encrypt_bytes(self, plaintext: bytes, aad: bytes) -> str:
        return PREFIX + base64.b64encode(_seal(self._key, plaintext, aad)).decode()

    def decrypt_bytes(self, token: str, aad: bytes) -> bytes:
        if not isinstance(token, str) or not token.startswith(PREFIX):
            raise TamperDetected("not a family-vault ciphertext")
        try:
            raw = base64.b64decode(token[len(PREFIX):], validate=True)
        except ValueError as e:
            raise TamperDetected("ciphertext is not valid base64") from e
        return _open(self._key, raw, aad)

    def encrypt_field(self, value: object, record_id: str, field: str) -> str:
        return self.encrypt_bytes(json.dumps(value).encode(), f"{record_id}:{field}".encode())

    def decrypt_field(self, token: str, record_id: str, field: str) -> object:
        return json.loads(self.decrypt_bytes(token, f"{record_id}:{field}".encode()))


def is_ciphertext(value: object) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


# ---------------------------------------------------------------- whole-vault export blobs


def encrypt_export(payload: dict, passphrase: str) -> bytes:
    """Encrypt a JSON-serialisable vault dump. The header (with KDF params) is authenticated."""
    params = KdfParams.new()
    key = derive_key(passphrase, params)
    header = json.dumps({"magic": EXPORT_MAGIC, "v": 1, "kdf": params.to_dict()}, sort_keys=True).encode()
    body = _seal(key, json.dumps(payload, sort_keys=True).encode(), header)
    return header + b"\n" + base64.b64encode(body)


def decrypt_export(blob: bytes, passphrase: str) -> dict:
    try:
        header_raw, body_b64 = blob.split(b"\n", 1)
        header = json.loads(header_raw)
        body = base64.b64decode(body_b64, validate=True)
    except ValueError as e:
        raise TamperDetected("export file is malformed") from e
    if header.get("magic") != EXPORT_MAGIC:
        raise TamperDetected("not a family-vault export")
    key = derive_key(passphrase, KdfParams.from_dict(header["kdf"]))
    try:
        return json.loads(_open(key, body, header_raw))
    except TamperDetected as e:
        raise WrongPassphrase("wrong passphrase or the export file was modified") from e
