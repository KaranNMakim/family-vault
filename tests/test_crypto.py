import base64

import pytest

from app.core.crypto import (
    CryptoError,
    KdfParams,
    TamperDetected,
    VaultCipher,
    WrongPassphrase,
    decrypt_export,
    encrypt_export,
    is_ciphertext,
)

PASS = "correct horse battery"


@pytest.fixture(scope="module")
def vault():
    return VaultCipher.create(PASS)


def test_roundtrip_field(vault):
    cipher, _, _ = vault
    tok = cipher.encrypt_field({"loc": "almirah"}, "n1", "location")
    assert is_ciphertext(tok) and "almirah" not in tok
    assert cipher.decrypt_field(tok, "n1", "location") == {"loc": "almirah"}


def test_nonce_is_random(vault):
    cipher, _, _ = vault
    assert cipher.encrypt_field("x", "n1", "f") != cipher.encrypt_field("x", "n1", "f")


def test_unlock_with_right_and_wrong_passphrase(vault):
    _, params, check = vault
    restored = KdfParams.from_dict(params.to_dict())
    VaultCipher.unlock(PASS, restored, check)
    with pytest.raises(WrongPassphrase):
        VaultCipher.unlock("wrong passphrase!", restored, check)


def test_tampered_ciphertext_detected(vault):
    cipher, _, _ = vault
    tok = cipher.encrypt_field("secret", "n1", "notes")
    raw = bytearray(base64.b64decode(tok[4:]))
    raw[-1] ^= 0x01
    with pytest.raises(TamperDetected):
        cipher.decrypt_field("fv1:" + base64.b64encode(bytes(raw)).decode(), "n1", "notes")


def test_ciphertext_bound_to_record_and_field(vault):
    cipher, _, _ = vault
    tok = cipher.encrypt_field("secret", "n1", "notes")
    with pytest.raises(TamperDetected):
        cipher.decrypt_field(tok, "n2", "notes")
    with pytest.raises(TamperDetected):
        cipher.decrypt_field(tok, "n1", "location")


@pytest.mark.parametrize("bad", ["plain", "fv1:!!!notbase64", "fv1:" + base64.b64encode(b"short").decode()])
def test_malformed_tokens(vault, bad):
    cipher, _, _ = vault
    with pytest.raises(TamperDetected):
        cipher.decrypt_field(bad, "n1", "f")


def test_short_passphrase_rejected():
    with pytest.raises(CryptoError):
        VaultCipher.create("short")


def test_bad_key_length():
    with pytest.raises(CryptoError):
        VaultCipher(b"123")


def test_unsupported_kdf():
    with pytest.raises(CryptoError):
        KdfParams.from_dict({"alg": "md5"})


def test_export_roundtrip_wrong_pass_and_tamper():
    blob = encrypt_export({"nodes": [1, 2]}, PASS)
    assert b"nodes" not in blob
    assert decrypt_export(blob, PASS) == {"nodes": [1, 2]}
    with pytest.raises(WrongPassphrase):
        decrypt_export(blob, "another passphrase")
    header, body = blob.split(b"\n", 1)
    tampered_header = header.replace(b'"v": 1', b'"v": 2')
    with pytest.raises(WrongPassphrase):
        decrypt_export(tampered_header + b"\n" + body, PASS)
    with pytest.raises(TamperDetected):
        decrypt_export(b"garbage", PASS)
    with pytest.raises(TamperDetected):
        decrypt_export(b'{"magic": "other"}\nAAAA', PASS)
