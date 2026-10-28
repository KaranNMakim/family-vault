"""Simulated emergency-access flow.

A trusted contact requests access -> a waiting period starts -> the owner is notified and may cancel ->
after the delay the request can be activated, opening a scoped read-only (nominee-like) view for a
limited time. Every transition is written to the audit log. Time comes from a simulated clock that the
demo can fast-forward (stored in the vault, so it survives restarts).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from app.core import audit
from app.core.estate import Estate

ACTIVE_DAYS = 7


class EmergencyError(ValueError):
    pass


class TooEarly(EmergencyError):
    def __init__(self, remaining: timedelta):
        self.remaining = remaining
        hours = round(remaining.total_seconds() / 3600, 1)
        super().__init__(f"waiting period not over: {hours} hours remaining")


class TimelineEvent(BaseModel):
    ts: datetime
    event: str
    actor: str


class AccessRequest(BaseModel):
    id: str
    requester_id: str
    requester_name: str
    reason: str
    status: str  # pending | cancelled | active | expired
    created_at: datetime
    wait_hours: int
    available_at: datetime
    expires_at: datetime | None = None
    timeline: list[TimelineEvent]


# ------------------------------------------------------------------ simulated clock
def now(store) -> datetime:
    rec = {r["id"]: r for r in store.get_records("clock")}.get("clock", {"offset_hours": 0})
    return datetime.now(UTC) + timedelta(hours=rec["offset_hours"])


def advance_clock(store, hours: float) -> datetime:
    rec = {r["id"]: r for r in store.get_records("clock")}.get("clock", {"id": "clock", "offset_hours": 0})
    rec["offset_hours"] = rec["offset_hours"] + hours
    store.put_record("clock", "clock", rec)
    return now(store)


# ------------------------------------------------------------------ persistence
def _save(store, req: AccessRequest) -> AccessRequest:
    store.put_record("access_request", req.id, req.model_dump(mode="json"))
    return req


def list_requests(store, at: datetime | None = None) -> list[AccessRequest]:
    at = at or now(store)
    out = []
    for raw in store.get_records("access_request"):
        req = AccessRequest.model_validate(raw)
        if req.status == "active" and req.expires_at and at >= req.expires_at:
            req.status = "expired"
            req.timeline.append(TimelineEvent(ts=req.expires_at, event="expired", actor="system"))
            _save(store, req)
            audit.append(store, "system", "system", "emergency.expired", req.id, ts=at)
        out.append(req)
    return sorted(out, key=lambda r: r.created_at)


def get_request(store, rid: str, at: datetime | None = None) -> AccessRequest:
    for r in list_requests(store, at):
        if r.id == rid:
            return r
    raise KeyError(rid)


def notify(store, to: str, text: str, at: datetime, ref: str) -> None:
    nid = f"n_{uuid.uuid4().hex[:8]}"
    store.put_record("notification", nid, {"id": nid, "to": to, "text": text, "ts": at.isoformat(), "ref": ref})


def notifications(store, to: str) -> list[dict]:
    return sorted([n for n in store.get_records("notification") if n["to"] == to], key=lambda n: n["ts"],
                  reverse=True)


# ------------------------------------------------------------------ transitions
def create_request(est: Estate, requester_id: str, reason: str, wait_hours: int,
                   at: datetime | None = None) -> AccessRequest:
    store = est.store
    at = at or now(store)
    person = est.node(requester_id)
    if person.cls != "Person" or not person.props.get("is_alive", True):
        raise EmergencyError("only a living person in the vault can request emergency access")
    if not est.nominated_assets(requester_id):
        raise EmergencyError("emergency access is for nominees; this person is not a nominee on any asset")
    if any(r.requester_id == requester_id and r.status in ("pending", "active") for r in list_requests(store, at)):
        raise EmergencyError("there is already an open request from this person")
    if not 0 <= wait_hours <= 24 * 30:
        raise EmergencyError("waiting period must be between 0 and 720 hours")
    req = AccessRequest(
        id=f"ar_{uuid.uuid4().hex[:8]}", requester_id=requester_id, requester_name=person.props["name"],
        reason=reason[:200], status="pending", created_at=at, wait_hours=wait_hours,
        available_at=at + timedelta(hours=wait_hours),
        timeline=[TimelineEvent(ts=at, event="requested", actor=requester_id),
                  TimelineEvent(ts=at, event="owner_notified", actor="system")],
    )
    owner = store.meta.get("owner", "owner")
    notify(store, owner, f"{person.props['name']} requested emergency access. It opens in {wait_hours} hours "
                         "unless you cancel.", at, req.id)
    audit.append(store, requester_id, "nominee", "emergency.requested", req.id, {"wait_hours": wait_hours}, ts=at)
    return _save(store, req)


def cancel_request(store, rid: str, by: str, at: datetime | None = None) -> AccessRequest:
    at = at or now(store)
    req = get_request(store, rid, at)
    if req.status not in ("pending", "active"):
        raise EmergencyError(f"request is already {req.status}")
    req.status = "cancelled"
    req.timeline.append(TimelineEvent(ts=at, event="cancelled", actor=by))
    notify(store, req.requester_id, "Your emergency-access request was cancelled by the vault owner.", at, rid)
    audit.append(store, by, "owner", "emergency.cancelled", rid, ts=at)
    return _save(store, req)


def activate_after_delay(store, rid: str, at: datetime | None = None) -> AccessRequest:
    at = at or now(store)
    req = get_request(store, rid, at)
    if req.status == "active":
        return req
    if req.status != "pending":
        raise EmergencyError(f"request is {req.status}")
    if at < req.available_at:
        raise TooEarly(req.available_at - at)
    req.status = "active"
    req.expires_at = at + timedelta(days=ACTIVE_DAYS)
    req.timeline.append(TimelineEvent(ts=at, event="activated", actor="system"))
    owner = store.meta.get("owner", "owner")
    notify(store, owner, f"Emergency access for {req.requester_name} is now open (read-only, {ACTIVE_DAYS} days).",
           at, rid)
    audit.append(store, "system", "system", "emergency.activated", rid, ts=at)
    return _save(store, req)
