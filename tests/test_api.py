"""API contract tests (synthetic seeded vaults in a temp dir)."""

import base64
import shutil
import sqlite3
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.api import sessions as sessions_mod
from app.api.main import create_app
from app.api.sessions import Registry
from app.core import totp


@pytest.fixture
def client(tmp_path, families, seeded_dir):
    for fam in families.values():
        shutil.copy(seeded_dir / f"{fam['id']}.db", tmp_path)
    reg = Registry(tmp_path)
    with TestClient(create_app(reg)) as c:
        c.families = families
        yield c
    reg.close_all()


def verify(client, challenge: dict, secret: str) -> dict:
    r = client.post("/session/verify", json={"challenge_id": challenge["challenge_id"], "code": totp.code_at(secret)})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def unlock(client, fid="family_a"):
    fam = client.families[fid]
    r = client.post("/session/unlock", json={"family_id": fid, "passphrase": fam["demo_passphrase"]})
    assert r.status_code == 200, r.text
    assert "token" not in r.json() and r.json()["method"] == "totp"  # passphrase alone is not enough
    return verify(client, r.json(), fam["totp_secret"])


def act_as(client, h, **body):
    r = client.post("/session/act-as", json=body, headers=h)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_public_endpoints(client):
    assert client.get("/health").json()["demo"] is True
    fams = client.get("/families").json()
    assert {f["id"] for f in fams} == {"family_a", "family_b", "family_c"}
    assert all("demo_passphrase" not in f for f in fams)
    assert "Person" in client.get("/ontology").json()["classes"]
    assert "death_of_earner" in client.get("/scenarios").json()
    assert "last 4" in client.get("/masking-policy").json()["why"]


def test_unlock_errors(client):
    bad = client.post("/session/unlock", json={"family_id": "family_a", "passphrase": "nope-nope"})
    assert bad.status_code == 401 and "attempt(s) left" in bad.json()["detail"]
    assert client.post("/session/unlock", json={"family_id": "nope", "passphrase": "x" * 9}).status_code == 404
    assert client.post("/session/unlock", json={"family_id": "../etc", "passphrase": "x" * 9}).status_code == 404
    assert client.get("/assets").status_code == 401
    assert client.get("/assets", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_owner_reads(client):
    h = unlock(client)
    s = client.get("/session", headers=h).json()
    assert s["principal"]["role"] == "owner" and s["can_write"] and "DEMO" in s["notice"]
    assets = client.get("/assets", headers=h).json()
    assert len(assets) == 7
    term = client.get("/assets/a_term", headers=h).json()
    assert term["props"]["masked_id"] == "XXXX4471"
    assert term["links"]["nominees"] == [{"id": "p_kabir", "name": "Kabir Mehta", "minor": True}]
    assert term["links"]["institution"]["name"].startswith("Bharat Life")
    kabir = client.get("/people/p_kabir", headers=h).json()
    assert kabir["inferred"]["is_minor"]["value"] is True and kabir["age"] == 8
    for path in ("/people", "/liabilities", "/documents", "/institutions", "/advisors"):
        assert client.get(path, headers=h).status_code == 200
    assert client.get("/assets/p_kabir", headers=h).status_code == 404
    assert client.get("/assets/nope", headers=h).status_code == 404


def test_gaps_readiness_graph(client):
    h = unlock(client, "family_c")
    gaps = client.get("/gaps", headers=h).json()
    assert len(gaps) == 12 and gaps[0]["severity"] == "critical" or gaps[0]["severity"] == "high"
    r = client.get("/readiness", headers=h).json()
    assert 0 <= r["score"] <= 100 and len(r["categories"]) == 6
    g = client.get("/graph", headers=h).json()
    assert "c_fd" in g["gaps_by_node"] and g["edges"]


def test_crud_relations_and_fix_flow(client):
    h = unlock(client)
    before = client.get("/readiness", headers=h).json()["score"]
    r = client.post("/relations", json={"src": "p_ananya", "rel": "guardian_of", "dst": "p_kabir"}, headers=h)
    assert r.status_code == 201
    after = client.get("/readiness", headers=h).json()["score"]
    assert after > before
    assert "G03:p_kabir" not in {g["key"] for g in client.get("/gaps", headers=h).json()}
    assert client.delete(f"/relations/{r.json()['id']}", headers=h).status_code == 200

    fd = {"asset_type": "fixed_deposit", "label": "New FD", "masked_id": "1234"}
    new = client.post("/assets", json={"props": fd}, headers=h)
    assert new.status_code == 201 and new.json()["props"]["masked_id"] == "XXXX1234"
    aid = new.json()["id"]
    up = client.patch(f"/assets/{aid}", json={"props": {"label": "Renamed FD"}}, headers=h)
    assert up.json()["props"]["label"] == "Renamed FD"
    assert client.patch(f"/people/{aid}", json={"props": {}}, headers=h).status_code == 404
    assert client.delete(f"/assets/{aid}", headers=h).status_code == 200
    assert client.delete("/people/a_term", headers=h).status_code == 404
    bad = client.post("/relations", json={"src": "a_term", "rel": "owns", "dst": "p_rohan"}, headers=h)
    assert bad.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"props": {"asset_type": "bank_account", "label": "Savings", "masked_id": "50100234567890"}},
        {"props": {"asset_type": "bank_account", "label": "Savings", "notes": "PIN is 4321"}},
        {"props": {"asset_type": "bank_account", "label": "Savings", "account_number": "1234"}},
        {"props": {"asset_type": "bank_account", "label": "Aadhaar 1234 5678 9012"}},
    ],
)
def test_full_numbers_and_secrets_rejected_with_explanation(client, payload):
    h = unlock(client)
    r = client.post("/assets", json=payload, headers=h)
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "masked_input_required" and "last 4" in body["why"]


def test_nominee_role_is_scoped_and_read_only(client):
    h = unlock(client)
    personas = client.get("/session/personas", headers=h).json()
    assert {"nominee", "spouse", "advisor", "owner"} <= {p["role"] for p in personas}
    n = act_as(client, h, role="nominee", person_id="p_ananya")
    ids = {a["id"] for a in client.get("/assets", headers=n).json()}
    assert ids == {"a_savings", "a_mf", "a_demat"}
    assert client.get("/assets/a_term", headers=n).status_code == 403
    assert client.post("/assets", json={"props": {"asset_type": "other", "label": "x"}}, headers=n).status_code == 403
    assert client.get("/readiness", headers=n).status_code == 403
    assert client.get("/audit", headers=n).status_code == 403
    assert client.post("/export", json={"passphrase": "x" * 10}, headers=n).status_code == 403
    assert client.post("/session/act-as", json={"role": "owner"}, headers=n).status_code == 403
    a = client.get("/assets/a_savings", headers=n).json()
    assert "notes" not in a["props"] and "knows" not in a["links"]
    cl = client.get("/checklist/death_of_earner", headers=n).json()
    assert {i for s in cl["steps"] for i in s["item_ids"]} <= ids
    gaps = {g["key"] for g in client.get("/gaps", headers=n).json()}
    assert "G03:p_kabir" not in gaps
    people = client.get("/people", headers=n).json()
    assert all("dob" not in p["props"] for p in people if p["id"] != "p_ananya")


def test_act_as_validation(client):
    h = unlock(client)
    assert client.post("/session/act-as", json={"role": "nominee", "person_id": "p_myra"}, headers=h).status_code == 422
    bad_adv = client.post("/session/act-as", json={"role": "advisor", "advisor_id": "p_myra"}, headers=h)
    assert bad_adv.status_code == 422
    assert client.post("/session/act-as", json={"role": "spouse", "person_id": "a_term"}, headers=h).status_code == 422
    adv = act_as(client, h, role="advisor", advisor_id="adv_desai")
    term = client.get("/assets/a_term", headers=adv).json()
    assert "masked_id" not in term["props"]
    sp = act_as(client, h, role="spouse", person_id="p_ananya", spouse_scope="shared")
    assert client.post("/assets", json={"props": {"asset_type": "other", "label": "x"}}, headers=sp).status_code == 403
    assert client.delete("/session", headers=sp).json() == {"ok": True}
    assert client.get("/session", headers=sp).status_code == 401


def test_checklist_and_pdf(client):
    h = unlock(client, "family_b")
    cl = client.get("/checklist/death_of_earner", headers=h).json()
    assert cl["blocked_count"] == 2 and "General guidance" in cl["disclaimer"]
    assert client.get("/checklist/incapacity?subject=p_vikram", headers=h).json()["subject_name"] == "Vikram Agarwal"
    assert client.get("/checklist/alien_invasion", headers=h).status_code == 404
    pdf = client.get("/checklist/loss_of_documents/pdf", headers=h)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_emergency_access_flow_with_cancel_and_activation(client):
    h = unlock(client, "family_c")
    n = act_as(client, h, role="nominee", person_id="p_lakshmi")
    r = client.post("/access-requests", json={"reason": "Arjun is in hospital", "wait_hours": 48}, headers=n)
    assert r.status_code == 201
    rid = r.json()["id"]
    assert client.post("/access-requests", json={"requester_id": "p_arjun"}, headers=n).status_code == 403
    assert "requested emergency access" in client.get("/notifications", headers=h).json()[0]["text"]
    early = client.post(f"/access-requests/{rid}/approve-after-delay", headers=n)
    assert early.status_code == 409 and early.json()["remaining_hours"] > 47
    assert client.get(f"/access-requests/{rid}/view", headers=n).status_code == 403
    assert client.post(f"/access-requests/{rid}/cancel", headers=n).status_code == 403
    # owner cancels
    assert client.post(f"/access-requests/{rid}/cancel", headers=h).json()["status"] == "cancelled"
    # new request, owner does not cancel, clock moves on
    rid2 = client.post("/access-requests", json={"reason": "again", "wait_hours": 24}, headers=n).json()["id"]
    client.post("/demo/clock/advance", json={"hours": 25}, headers=h)
    assert client.post(f"/access-requests/{rid2}/approve-after-delay", headers=n).json()["status"] == "active"
    view = client.get(f"/access-requests/{rid2}/view", headers=n).json()
    assert set(view["graph"]["visible_items"]) == {"c_savings", "c_fd", "c_demat", "c_mf", "c_policy"}
    assert any(p["role"] == "emergency" for p in client.get("/session/personas", headers=h).json())
    em = act_as(client, h, role="emergency", person_id="p_lakshmi", access_request_id=rid2)
    assert client.get("/assets/c_old_acct", headers=em).status_code == 403
    assert [r["status"] for r in client.get("/access-requests", headers=n).json()] == ["cancelled", "active"]
    actions = [e["action"] for e in client.get("/audit", headers=h).json()["entries"]]
    assert {"emergency.requested", "emergency.cancelled", "emergency.activated", "emergency.view"} <= set(actions)
    assert client.post("/access-requests/nope/cancel", headers=h).status_code == 404
    assert client.get("/access-requests/nope/view", headers=h).status_code == 404
    assert client.post("/access-requests/nope/approve-after-delay", headers=h).status_code == 404
    assert client.get("/demo/clock", headers=h).status_code == 200


def test_audit_log(client):
    h = unlock(client)
    client.get("/assets", headers=h)
    a = client.get("/audit", headers=h).json()
    assert a["chain_valid"] is True
    assert {"vault.unlocked", "assets.list"} <= {e["action"] for e in a["entries"]}


def test_export_import_roundtrip(client):
    h = unlock(client)
    blob = client.post("/export", json={"passphrase": "export-pass-123"}, headers=h)
    assert blob.status_code == 200 and b"Rohan" not in blob.content
    b64 = base64.b64encode(blob.content).decode()
    bad = client.post("/import", json={"blob_b64": b64, "export_passphrase": "wrong-pass-123",
                                       "new_vault_passphrase": "new-vault-pass"})
    assert bad.status_code == 400
    junk = client.post("/import", json={"blob_b64": "AAAA", "export_passphrase": "x", "new_vault_passphrase": "y" * 8})
    assert junk.status_code == 400
    ok = client.post("/import", json={"blob_b64": b64, "export_passphrase": "export-pass-123",
                                      "display_name": "Mehta copy", "new_vault_passphrase": "new-vault-pass"})
    assert ok.status_code == 200 and ok.json()["enroll"]["secret"]  # imported vault enrols a new authenticator
    h2 = verify(client, ok.json(), ok.json()["enroll"]["secret"])
    assert len(client.get("/assets", headers=h2).json()) == 7
    assert client.get("/session", headers=h2).json()["family"]["display_name"] == "Mehta copy"


def test_onboarding_flow_creates_graph_and_gaps(client):
    r = client.post("/vaults", json={"display_name": "Test onboarding family", "passphrase": "onboard-pass-1"})
    assert r.status_code == 200
    enroll = r.json()["enroll"]
    assert enroll["otpauth_uri"].startswith("otpauth://totp/") and enroll["secret"] in enroll["otpauth_uri"]
    h = verify(client, r.json(), enroll["secret"])
    q = client.get("/onboarding", headers=h).json()
    assert q["question"]["id"] == "household.owner" and not q["question"]["skippable"]
    assert client.post("/onboarding/answer", json={"skip": True}, headers=h).status_code == 422
    q = client.post("/onboarding/answer", json={"name": "Meera Iyer", "dob": "1985-02-02"}, headers=h).json()
    owner = q["last_created"][0]
    assert client.get("/session", headers=h).json()["principal"]["person_id"] == owner
    q = client.post("/onboarding/answer", json={"name": "Tara Iyer", "relation": "daughter", "dob": "2019-01-01"},
                    headers=h).json()
    tara = q["last_created"][0]
    q = client.post("/onboarding/answer", json={"done": True}, headers=h).json()
    assert q["question"]["id"] == "insurance.has" and q["progress"]["done"] == 1
    assert "have an insurance policy" in q["question"]["prompt"]
    q = client.post("/onboarding/answer", json={"yes": True}, headers=h).json()
    assert q["question"]["input"] == "asset_form"
    bad = client.post("/onboarding/answer", json={"label": "Term plan", "masked_id": "123456789012"}, headers=h)
    assert bad.status_code == 422 and "last 4" in bad.json()["why"]
    q = client.post("/onboarding/answer", json={
        "label": "Term plan", "masked_id": "7788", "institution_name": "Kaveri Life (fictional)",
        "owners": [owner], "nominees": [tara], "has_document": True, "document_location": "Steel cupboard"},
        headers=h).json()
    assert q["question"]["id"] == "insurance.another" and len(q["last_created"]) == 2
    q = client.post("/onboarding/answer", json={"yes": False}, headers=h).json()
    assert q["question"]["section"] == "bank_account"
    for _ in range(7):  # skip remaining sections
        q = client.post("/onboarding/answer", json={"skip": True}, headers=h).json()
    assert q["question"]["id"] == "review" and q["progress"]["percent"] == 100
    keys = {g["key"] for g in client.get("/gaps", headers=h).json()}
    assert f"G03:{tara}" in keys  # minor nominee without guardian
    bad_owner = client.post("/onboarding/reset", headers=h)
    assert bad_owner.json()["question"]["id"] == "household.member"
    assert client.post("/vaults", json={"display_name": "PAN ABCDE1234F", "passphrase": "x" * 8}).status_code == 422


# ---------------------------------------------------------------------------------------------- 2-step unlock
def _challenge(client, fid="family_a"):
    fam = client.families[fid]
    return client.post("/session/unlock", json={"family_id": fid, "passphrase": fam["demo_passphrase"]}).json()


def test_wrong_code_and_replay_are_rejected(client):
    secret = client.families["family_a"]["totp_secret"]
    ch = _challenge(client)
    wrong = "000000" if totp.code_at(secret) != "000000" else "111111"
    bad = client.post("/session/verify", json={"challenge_id": ch["challenge_id"], "code": wrong})
    assert bad.status_code == 401 and "attempt(s) left" in bad.json()["detail"]
    verify(client, ch, secret)
    # The same code cannot be used again (replay), even after a fresh passphrase step.
    ch2 = _challenge(client)
    again = client.post("/session/verify", json={"challenge_id": ch2["challenge_id"], "code": totp.code_at(secret)})
    assert again.status_code == 401
    assert client.post("/session/verify", json={"challenge_id": "nope", "code": "123456"}).status_code == 401


def test_code_attempts_and_passphrase_failures_lock_the_vault(client):
    secret = client.families["family_b"]["totp_secret"]
    wrong = "000000" if totp.code_at(secret) != "000000" else "111111"
    ch = _challenge(client, "family_b")
    for _ in range(sessions_mod.MAX_CODE_ATTEMPTS):
        client.post("/session/verify", json={"challenge_id": ch["challenge_id"], "code": wrong})
    locked = client.post("/session/verify", json={"challenge_id": ch["challenge_id"], "code": wrong})
    assert locked.status_code == 429
    right_pass = {"family_id": "family_b", "passphrase": client.families["family_b"]["demo_passphrase"]}
    assert client.post("/session/unlock", json=right_pass).status_code == 429
    for _ in range(sessions_mod.MAX_PASSPHRASE_FAILURES):
        r = client.post("/session/unlock", json={"family_id": "family_c", "passphrase": "wrong-passphrase"})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    ok_pass = {"family_id": "family_c", "passphrase": client.families["family_c"]["demo_passphrase"]}
    assert client.post("/session/unlock", json=ok_pass).status_code == 429  # locked even with the right one


def test_failed_unlocks_are_audited(client):
    client.post("/session/unlock", json={"family_id": "family_a", "passphrase": "wrong-passphrase"})
    h = unlock(client)
    entries = client.get("/audit", headers=h).json()["entries"]
    assert "vault.unlock_failed" in [e["action"] for e in entries]
    unlocked = next(e for e in entries if e["action"] == "vault.unlocked")
    assert unlocked["details"]["second_factor"] == "totp"


def test_idle_session_expires(client):
    h = unlock(client)
    s = client.get("/session", headers=h).json()
    assert s["security"]["two_factor"] is True and s["security"]["idle_timeout_minutes"] == 15
    reg = client.app.state.registry
    reg.sessions[h["Authorization"][7:]].last_seen -= sessions_mod.IDLE_TIMEOUT + timedelta(seconds=1)
    assert client.get("/session", headers=h).status_code == 401


def test_expired_challenge(client):
    ch = _challenge(client)
    challenge = client.app.state.registry.challenges[ch["challenge_id"]]
    challenge.created_at -= sessions_mod.CHALLENGE_TTL + timedelta(seconds=1)
    r = client.post("/session/verify", json={"challenge_id": ch["challenge_id"], "code": "123456"})
    assert r.status_code == 401 and "expired" in r.json()["detail"]


def test_vault_without_second_factor_enrols_one(client):
    reg = client.app.state.registry
    db = sqlite3.connect(reg.path("family_a"))
    db.execute("DELETE FROM meta WHERE key='totp'")
    db.commit()
    db.close()
    ch = _challenge(client)
    assert ch["enroll"]["secret"]
    verify(client, ch, ch["enroll"]["secret"])
