from datetime import UTC, datetime, timedelta

import pytest

from app.core import audit, emergency
from app.core.access import (
    AccessDenied,
    Principal,
    require_item,
    require_write,
    scoped_gaps,
    scoped_graph,
    visible_items,
)
from app.core.gaps import detect_gaps

T0 = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


# ------------------------------------------------------------------ access
def test_owner_sees_everything(family_store, est_factory):
    est = est_factory(family_store("family_a"))
    view = scoped_graph(est, Principal(role="owner", person_id="p_rohan"))
    assert len(view["nodes"]) == est.store.g.number_of_nodes()
    assert any(n["props"].get("notes") for n in view["nodes"])


def test_nominee_scope_is_only_their_assets(family_store, est_factory):
    est = est_factory(family_store("family_a"))
    pr = Principal(role="nominee", person_id="p_ananya")
    assert visible_items(est, pr) == {"a_savings", "a_mf", "a_demat"}
    view = scoped_graph(est, pr)
    ids = {n["id"] for n in view["nodes"]}
    assert "a_term" not in ids and "a_fd_ananya" not in ids and "l_homeloan" not in ids
    assert "i_sahyadri" in ids  # institution of a visible asset
    assert all("notes" not in n["props"] for n in view["nodes"])
    rohan = next(n for n in view["nodes"] if n["id"] == "p_rohan")
    assert "dob" not in rohan["props"]
    assert not any(e["rel"] == "knows_about" for e in view["edges"])
    gaps = scoped_gaps(detect_gaps(est), est, pr)
    assert {g.key for g in gaps} == {"G05:a_mf", "G06:a_demat", "G02:p_rohan"}
    with pytest.raises(AccessDenied):
        require_item(est, pr, "a_term")
    with pytest.raises(AccessDenied):
        require_write(pr)


def test_advisor_sees_no_sensitive_fields(family_store, est_factory):
    est = est_factory(family_store("family_a"))
    pr = Principal(role="advisor", advisor_id="adv_desai")
    view = scoped_graph(est, pr)
    term = next(n for n in view["nodes"] if n["id"] == "a_term")
    assert "masked_id" not in term["props"] and "notes" not in term["props"]
    assert visible_items(est, pr) == {"a_term"}


def test_spouse_full_vs_shared(family_store, est_factory):
    est = est_factory(family_store("family_b"))
    full = Principal(role="spouse", person_id="p_neha")
    shared = Principal(role="spouse", person_id="p_neha", spouse_scope="shared")
    assert full.can_write and not shared.can_write
    assert visible_items(est, full) == {n.id for n in est.assets() + est.liabilities()}
    assert visible_items(est, shared) == {"b_lic", "b_pension", "b_house", "b_v_demat", "b_v_savings", "b_v_mf",
                                          "b_n_ppf"}
    assert Principal(role="owner").actor == "anonymous"


# ------------------------------------------------------------------ emergency access
def test_request_wait_activate_expire(fresh, est_factory):
    s = fresh("family_c")
    est = est_factory(s)
    req = emergency.create_request(est, "p_lakshmi", "Arjun is in hospital", 72, at=T0)
    assert req.status == "pending" and req.available_at == T0 + timedelta(hours=72)
    assert "requested emergency access" in emergency.notifications(s, "p_arjun")[0]["text"]
    with pytest.raises(emergency.TooEarly, match="hours remaining"):
        emergency.activate_after_delay(s, req.id, at=T0 + timedelta(hours=71))
    active = emergency.activate_after_delay(s, req.id, at=T0 + timedelta(hours=72))
    assert active.status == "active"
    assert emergency.activate_after_delay(s, req.id, at=T0 + timedelta(hours=73)).status == "active"
    later = T0 + timedelta(hours=72, days=8)
    assert emergency.get_request(s, req.id, at=later).status == "expired"
    events = [e.event for e in emergency.get_request(s, req.id, at=later).timeline]
    assert events == ["requested", "owner_notified", "activated", "expired"]
    actions = [e["action"] for e in audit.entries(s)]
    assert actions[:3] == ["emergency.expired", "emergency.activated", "emergency.requested"]
    s.close()


def test_owner_cancels(fresh, est_factory):
    s = fresh("family_c")
    est = est_factory(s)
    req = emergency.create_request(est, "p_lakshmi", "test", 48, at=T0)
    with pytest.raises(emergency.EmergencyError, match="already an open request"):
        emergency.create_request(est, "p_lakshmi", "again", 48, at=T0)
    c = emergency.cancel_request(s, req.id, "p_arjun", at=T0 + timedelta(hours=1))
    assert c.status == "cancelled"
    with pytest.raises(emergency.EmergencyError, match="cancelled"):
        emergency.activate_after_delay(s, req.id, at=T0 + timedelta(hours=100))
    with pytest.raises(emergency.EmergencyError):
        emergency.cancel_request(s, req.id, "p_arjun", at=T0 + timedelta(hours=2))
    assert "cancelled" in emergency.notifications(s, "p_lakshmi")[0]["text"]
    s.close()


@pytest.mark.parametrize("pid,hours,msg", [("p_gopal", 24, "not a nominee"), ("p_lakshmi", 9999, "between"),
                                           ("i_malabar", 24, "living person")])
def test_invalid_requests(fresh, est_factory, pid, hours, msg):
    s = fresh("family_c")
    with pytest.raises(emergency.EmergencyError, match=msg):
        emergency.create_request(est_factory(s), pid, "x", hours, at=T0)
    s.close()


def test_minor_cannot_request(fresh, est_factory):
    s = fresh("family_a")
    with pytest.raises(emergency.EmergencyError, match="minor"):
        emergency.create_request(est_factory(s), "p_kabir", "x", 24, at=T0)
    s.close()



def test_simulated_clock(fresh):
    s = fresh("family_a")
    before = emergency.now(s)
    after = emergency.advance_clock(s, 72)
    assert after - before >= timedelta(hours=71.9)
    with pytest.raises(KeyError):
        emergency.get_request(s, "nope")
    s.close()


# ------------------------------------------------------------------ audit chain
def test_audit_chain_detects_tampering(fresh):
    s = fresh("family_a")
    for i in range(3):
        audit.append(s, "p_rohan", "owner", "asset.update", f"a{i}", {"masked_id": "1234", "note": "acct 987654321"})
    assert audit.verify(s) == (True, None)
    e = audit.entries(s)[0]
    assert e["details"]["masked_id"] == "[REDACTED]" and "987654321" not in e["details"]["note"]
    s.db.execute("UPDATE audit SET body = replace(body, 'a1', 'zz') WHERE seq = 2")
    assert audit.verify(s) == (False, 2)
    s.db.execute("DELETE FROM audit WHERE seq = 2")
    assert audit.verify(s)[0] is False
    s.close()
