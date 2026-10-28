import base64

from app.core import totp

# RFC 6238 Appendix B secret ("12345678901234567890"), SHA-1, truncated to 6 digits.
RFC_SECRET = base64.b32encode(b"12345678901234567890").decode()


def test_rfc6238_vectors():
    assert totp.code_at(RFC_SECRET, 59) == "287082"
    assert totp.code_at(RFC_SECRET, 1111111109) == "081804"
    assert totp.code_at(RFC_SECRET, 1234567890) == "005924"


def test_verify_window_replay_and_format():
    t = 1_000_000_000
    code = totp.code_at(RFC_SECRET, t)
    step = totp.verify(RFC_SECRET, code, t=t)
    assert step == t // 30
    assert totp.verify(RFC_SECRET, totp.code_at(RFC_SECRET, t - 30), t=t) == step - 1  # one step of clock drift
    assert totp.verify(RFC_SECRET, totp.code_at(RFC_SECRET, t - 90), t=t) is None
    assert totp.verify(RFC_SECRET, code, t=t, last_step=step) is None  # replay
    assert totp.verify(RFC_SECRET, "12ab56", t=t) is None
    assert totp.verify(RFC_SECRET, "", t=t) is None


def test_new_secret_and_uri():
    s = totp.new_secret()
    assert len(s) == 32 and totp.code_at(s).isdigit()
    uri = totp.provisioning_uri(s, "Iyer family")
    assert uri.startswith("otpauth://totp/family-vault%20demo%3AIyer%20family?secret=" + s)
