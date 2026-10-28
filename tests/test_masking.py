import pytest

from app.core.masking import MaskingError, check_free_text, mask_identifier, reject_forbidden_keys


@pytest.mark.parametrize(
    "value,expected",
    [("1234", "XXXX1234"), ("XXXX1234", "XXXX1234"), ("****1234", "XXXX1234"), ("xx-xx-ab12", "XXXXAB12"),
     ("  ••••9876 ", "XXXX9876"), ("A1", "XXXXA1")],
)
def test_masked_ids_accepted(value, expected):
    assert mask_identifier(value) == expected


@pytest.mark.parametrize(
    "value",
    ["123456789012", "50100234567890", "4111 1111 1111 1111", "XXXX12345", "ABCDE1234F", "", "12@4", "SBIN0001234"],
)
def test_full_numbers_rejected(value):
    with pytest.raises(MaskingError) as e:
        mask_identifier(value)
    assert "last 4" in str(e.value)


@pytest.mark.parametrize(
    "text",
    [
        "Aadhaar 1234 5678 9012",
        "account no 50100234567890",
        "card 4111-1111-1111-1111",
        "PAN ABCDE1234F",
        "net banking password is Tiger@123",
        "ATM PIN 4321",
        "otp: 889911",
        "my mpin = 1111",
    ],
)
def test_free_text_rejects_secrets_and_ids(text):
    with pytest.raises(MaskingError):
        check_free_text(text, "notes")


@pytest.mark.parametrize(
    "text",
    ["Kept in the Godrej almirah, top shelf", "Matures on 2026-11-20", "Renewal due 15/12/2026",
     "Ask Ramesh uncle (LIC agent)", "Pin it on the fridge", "Locker no 12 at the branch"],
)
def test_free_text_allows_normal_notes(text):
    assert check_free_text(text, "notes") == text


def test_forbidden_keys_rejected_recursively():
    with pytest.raises(MaskingError) as e:
        reject_forbidden_keys({"asset": {"label": "x", "account_number": "1"}})
    assert e.value.field == "asset.account_number"
    with pytest.raises(MaskingError):
        reject_forbidden_keys([{"PIN": "1"}])
    reject_forbidden_keys({"label": "ok", "masked_id": "1234"})


def test_error_payload_explains_why():
    with pytest.raises(MaskingError) as e:
        mask_identifier("123456789")
    d = e.value.to_dict()
    assert d["field"] == "masked_id" and "last 4" in d["why"]
