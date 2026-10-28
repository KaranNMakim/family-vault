import sqlite3

import pytest

from app.core.crypto import WrongPassphrase
from app.core.masking import MaskingError
from app.kg.ontology import OntologyError
from app.kg.store import NetworkXSQLiteStore, NotFound
from tests.conftest import PASS, P


def test_crud_and_reopen(empty_store, tmp_path):
    s = empty_store
    p = s.add_node("Person", {"name": "Asha", "dob": "1970-01-01"}, P, node_id="p1")
    assert p.props["is_alive"] is True
    a = s.add_node("Asset", {"asset_type": "bank_account", "label": "Savings", "masked_id": "9876",
                             "notes": "Kept near the TV"}, P)
    e = s.add_edge("p1", "owns", a.id, P, {"role": "owner"})
    assert s.edges(rel="owns", src="p1")[0].id == e.id
    s.update_node(a.id, {"label": "Main savings"}, P)
    s.close()

    s2 = NetworkXSQLiteStore.open(tmp_path / "empty.db", PASS)
    assert s2.get_node(a.id).props == {"asset_type": "bank_account", "label": "Main savings",
                                       "masked_id": "XXXX9876", "notes": "Kept near the TV", "value_band": "unknown"}
    assert s2.get_node("p1").prov.method == "human"
    assert s2.meta["display_name"] == "Test"
    assert NetworkXSQLiteStore.read_public_meta(tmp_path / "empty.db")["id"] == "t"
    s2.delete_edge(e.id)
    assert not s2.edges(rel="owns")
    s2.delete_node(a.id)
    with pytest.raises(NotFound):
        s2.get_node(a.id)
    with pytest.raises(NotFound):
        s2.delete_edge("p1|owns|nope")
    s2.close()


def test_sensitive_fields_are_ciphertext_on_disk(empty_store, tmp_path):
    empty_store.add_node("Document", {"doc_type": "will", "label": "Will", "location": "UniqueSpotZebra cupboard"}, P)
    empty_store.add_node("Person", {"name": "Bina", "dob": "1999-09-09"}, P)
    raw = (tmp_path / "empty.db").read_bytes()
    assert b"UniqueSpotZebra" not in raw
    assert b"1999-09-09" not in raw
    rows = sqlite3.connect(tmp_path / "empty.db").execute("SELECT props FROM nodes").fetchall()
    assert all("fv1:" in r[0] for r in rows)


def test_wrong_passphrase(empty_store, tmp_path):
    with pytest.raises(WrongPassphrase):
        NetworkXSQLiteStore.open(tmp_path / "empty.db", "not the passphrase")
    with pytest.raises(FileNotFoundError):
        NetworkXSQLiteStore.open(tmp_path / "missing.db", PASS)
    with pytest.raises(FileExistsError):
        NetworkXSQLiteStore.create(tmp_path / "empty.db", PASS)


def test_validation_on_write(empty_store):
    s = empty_store
    s.add_node("Person", {"name": "A"}, P, node_id="p1")
    with pytest.raises(OntologyError):
        s.add_node("Person", {"name": "B"}, P, node_id="p1")
    with pytest.raises(MaskingError):
        s.add_node("Asset", {"asset_type": "demat", "label": "D", "masked_id": "1203450000123456"}, P)
    a = s.add_node("Asset", {"asset_type": "demat", "label": "D"}, P)
    with pytest.raises(OntologyError):
        s.add_edge(a.id, "owns", "p1", P)
    s.add_edge("p1", "owns", a.id, P)
    with pytest.raises(OntologyError):
        s.add_edge("p1", "owns", a.id, P)
    with pytest.raises(OntologyError):
        s.update_node(a.id, {"asset_type": "nope"}, P)


def test_dump_and_load_roundtrip(fresh, tmp_path):
    src = fresh("family_b")
    src.put_record("access_request", "r1", {"id": "r1", "status": "pending"})
    dump = src.dump()
    dst = NetworkXSQLiteStore.create(tmp_path / "copy.db", PASS)
    dst.load_dump(dump)
    assert dst.dump() == dump
    with pytest.raises(OntologyError):
        dst.load_dump(dump)
    dst.close()
    src.close()
