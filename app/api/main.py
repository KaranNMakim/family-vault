"""FastAPI application: family-vault demo API (synthetic data only)."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from app import __version__
from app.api.pdf import checklist_pdf
from app.api.sessions import Registry, Session
from app.config import get_settings
from app.core import audit, emergency, onboarding
from app.core.access import (
    AccessDenied,
    Principal,
    redact_node,
    require_item,
    require_write,
    scoped_gaps,
    scoped_graph,
    visible_items,
)
from app.core.checklist import SCENARIOS, generate
from app.core.crypto import CryptoError, TamperDetected, WrongPassphrase, decrypt_export, encrypt_export
from app.core.estate import Estate
from app.core.gaps import detect_gaps
from app.core.masking import WHY, MaskingError, check_free_text, reject_forbidden_keys
from app.core.readiness import readiness
from app.kg.ontology import OntologyError, get_ontology
from app.kg.provenance import human
from app.kg.store import NotFound
from app.logs import configure_logging, get_logger

log = get_logger("api")

ENTITIES = {"people": "Person", "assets": "Asset", "liabilities": "Liability", "documents": "Document",
            "institutions": "Institution", "advisors": "Advisor"}
DEMO_NOTICE = "DEMO ONLY - synthetic data. Do not enter real account numbers, ID numbers or passwords."


# ---------------------------------------------------------------------------------------------- models
class UnlockIn(BaseModel):
    family_id: str
    passphrase: str


class CreateVaultIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    passphrase: str = Field(min_length=8)


class ActAsIn(BaseModel):
    role: Literal["owner", "spouse", "nominee", "advisor", "emergency"]
    person_id: str | None = None
    advisor_id: str | None = None
    spouse_scope: Literal["full", "shared"] = "full"
    access_request_id: str | None = None


class NodeIn(BaseModel):
    props: dict[str, Any]
    id: str | None = Field(default=None, pattern=r"^[a-z0-9_]{2,40}$")


class PatchIn(BaseModel):
    props: dict[str, Any]


class RelationIn(BaseModel):
    src: str
    rel: str
    dst: str
    props: dict[str, Any] = {}


class AccessRequestIn(BaseModel):
    requester_id: str | None = None
    reason: str = Field(default="", max_length=200)
    wait_hours: int | None = None


class ClockIn(BaseModel):
    hours: float = Field(gt=0, le=24 * 60)


class ExportIn(BaseModel):
    passphrase: str = Field(min_length=8)


class ImportIn(BaseModel):
    blob_b64: str
    export_passphrase: str
    display_name: str = Field(default="Imported family", max_length=80)
    new_vault_passphrase: str = Field(min_length=8)


@dataclass
class Ctx:
    session: Session
    est: Estate

    @property
    def pr(self) -> Principal:
        return self.session.principal

    @property
    def store(self):
        return self.est.store

    def audit(self, action: str, target: str = "", details: dict | None = None) -> None:
        audit.append(self.store, self.pr.actor, self.pr.role, action, target, details)


# ---------------------------------------------------------------------------------------------- app
def create_app(registry: Registry | None = None) -> FastAPI:
    configure_logging()
    settings = get_settings()
    reg = registry or Registry()

    async def guard_body(request: Request) -> None:
        """Reject forbidden keys (password, pin, aadhaar, account_number, ...) anywhere in a JSON body."""
        if request.method in ("POST", "PUT", "PATCH") and "json" in request.headers.get("content-type", ""):
            body = await request.body()
            try:
                data = json.loads(body) if body else None
            except ValueError:
                return  # malformed JSON: FastAPI reports it
            reject_forbidden_keys(data)

    api = FastAPI(title="family-vault (DEMO - synthetic data only)", version=__version__,
                  dependencies=[Depends(guard_body)])
    api.state.registry = reg
    api.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["*"],
                       allow_headers=["*"], expose_headers=["Content-Disposition"])

    # ------------------------------------------------------------------ errors
    @api.exception_handler(MaskingError)
    async def _masking(_: Request, e: MaskingError):
        return JSONResponse(status_code=422, content={"error": "masked_input_required", **e.to_dict()})

    @api.exception_handler(OntologyError)
    async def _onto(_: Request, e: OntologyError):
        return JSONResponse(status_code=422, content={"error": "invalid", "detail": str(e)})

    @api.exception_handler(AccessDenied)
    async def _denied(_: Request, e: AccessDenied):
        return JSONResponse(status_code=403, content={"error": "forbidden", "detail": str(e)})

    @api.exception_handler(NotFound)
    async def _nf(_: Request, e: NotFound):
        return JSONResponse(status_code=404, content={"error": "not_found", "detail": str(e)})

    @api.exception_handler(emergency.TooEarly)
    async def _early(_: Request, e: emergency.TooEarly):
        return JSONResponse(status_code=409, content={"error": "too_early", "detail": str(e),
                                                      "remaining_hours": round(e.remaining.total_seconds() / 3600, 1)})

    @api.exception_handler(emergency.EmergencyError)
    async def _emerg(_: Request, e: emergency.EmergencyError):
        return JSONResponse(status_code=409, content={"error": "conflict", "detail": str(e)})

    # ------------------------------------------------------------------ auth
    def ctx(authorization: str = Header(default="")) -> Ctx:
        token = authorization.removeprefix("Bearer ").strip()
        try:
            s = reg.get(token)
            return Ctx(s, reg.estate(s.family_id))
        except KeyError as e:
            raise HTTPException(401, "not unlocked - unlock the vault first") from e

    def session_out(s: Session) -> dict:
        store = reg.store(s.family_id)
        return {"token": s.token, "family": store.meta, "principal": s.principal.model_dump(),
                "can_write": s.principal.can_write, "notice": DEMO_NOTICE}

    # ------------------------------------------------------------------ public
    @api.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__, "llm_mode": settings.llm_mode, "demo": True,
                "notice": DEMO_NOTICE, "as_of": settings.as_of.isoformat()}

    @api.get("/ontology")
    def ontology(format: str = "json"):
        onto = get_ontology()
        if format == "turtle":
            return PlainTextResponse(onto.to_turtle(), media_type="text/turtle")
        if format == "jsonld":
            return PlainTextResponse(onto.to_jsonld(), media_type="application/ld+json")
        return onto.model_dump()

    @api.get("/families")
    def families() -> list[dict]:
        return reg.families()

    # ------------------------------------------------------------------ sessions
    @api.post("/session/unlock")
    def unlock(body: UnlockIn) -> dict:
        try:
            store = reg.unlock(body.family_id, body.passphrase)
        except (KeyError, FileNotFoundError) as e:
            raise HTTPException(404, "no such family vault") from e
        except WrongPassphrase as e:
            raise HTTPException(401, "wrong passphrase") from e
        owner = store.meta.get("owner")
        s = reg.new_session(body.family_id, Principal(role="owner", person_id=owner))
        audit.append(store, owner or "owner", "owner", "vault.unlocked")
        return session_out(s)

    @api.post("/vaults")
    def create_vault(body: CreateVaultIn) -> dict:
        check_free_text(body.display_name, "display_name")
        fid, store = reg.create(body.display_name, body.passphrase)
        s = reg.new_session(fid, Principal(role="owner"))
        audit.append(store, "owner", "owner", "vault.created", fid)
        return session_out(s)

    @api.get("/session")
    def get_session(c: Ctx = Depends(ctx)) -> dict:
        return session_out(c.session)

    @api.get("/session/personas")
    def personas(c: Ctx = Depends(ctx)) -> list[dict]:
        """Demo role switcher: who can this vault be viewed as."""
        est, out = c.est, []
        owner = c.store.meta.get("owner")
        if owner:
            out.append({"role": "owner", "person_id": owner, "label": f"{est.name(owner)} (owner)"})
        for p in est.people():
            if p.props.get("relation") == "spouse" and p.props.get("is_alive", True):
                out.append({"role": "spouse", "person_id": p.id, "label": f"{p.props['name']} (spouse)"})
        for p in est.people():
            if est.nominated_assets(p.id) and p.props.get("is_alive", True) and p.id != owner:
                out.append({"role": "nominee", "person_id": p.id, "label": f"{p.props['name']} (nominee)"})
        for a in c.store.nodes("Advisor"):
            out.append({"role": "advisor", "advisor_id": a.id, "label": f"{a.props['name']} (advisor)"})
        for r in emergency.list_requests(c.store):
            if r.status == "active":
                out.append({"role": "emergency", "person_id": r.requester_id, "access_request_id": r.id,
                            "label": f"{r.requester_name} (emergency access)"})
        return out

    @api.post("/session/act-as")
    def act_as(body: ActAsIn, c: Ctx = Depends(ctx)) -> dict:
        if c.pr.role != "owner":
            raise AccessDenied("only the owner session can switch roles (demo)")
        est = c.est
        if body.role in ("spouse", "nominee", "emergency", "owner"):
            pid = body.person_id or c.store.meta.get("owner")
            if not pid or est.node(pid).cls != "Person":
                raise HTTPException(422, "person_id must be a person in this vault")
            if body.role == "nominee" and not est.nominated_assets(pid):
                raise HTTPException(422, "this person is not a nominee on any asset")
            if body.role == "emergency":
                req = emergency.get_request(c.store, body.access_request_id or "")
                if req.status != "active" or req.requester_id != pid:
                    raise AccessDenied("no active emergency access for this person")
        elif body.role == "advisor" and (not body.advisor_id or est.node(body.advisor_id).cls != "Advisor"):
            raise HTTPException(422, "advisor_id must be an advisor in this vault")
        pr = Principal(**body.model_dump())
        if pr.role == "owner":
            pr.person_id = c.store.meta.get("owner")
        s = reg.new_session(c.session.family_id, pr)
        audit.append(c.store, pr.actor, pr.role, "session.started", details={"via": "role_switcher"})
        return session_out(s)

    @api.delete("/session")
    def lock(c: Ctx = Depends(ctx)) -> dict:
        reg.end(c.session.token)
        return {"ok": True}

    # ------------------------------------------------------------------ entities
    def item_view(c: Ctx, node) -> dict:
        est = c.est
        d = redact_node(est, c.pr, node)
        if node.cls in ("Asset", "Liability"):
            inst = est.institution(node.id)
            d["links"] = {
                "owners": [{"id": e.src, "name": est.name(e.src), "role": e.props.get("role", "owner")}
                           for e in c.store.edges(rel="owns", dst=node.id)],
                "nominees": [{"id": n, "name": est.name(n), "minor": est.is_minor(n)} for n in est.nominees(node.id)],
                "institution": {"id": inst.id, "name": inst.props["name"]} if inst else None,
                "documents": [redact_node(est, c.pr, doc) for doc in est.documents(node.id)],
                "advisors": [{"id": a, "name": est.name(a)} for a in est.advisors(node.id)],
            }
            if c.pr.role not in ("nominee", "emergency", "advisor"):
                d["links"]["knows"] = [{"id": k, "name": est.name(k)} for k in est.knowers(node.id)]
        if node.cls == "Person":
            d["inferred"] = est.inferred_facts(node.id)
            if c.pr.role in ("owner", "spouse"):
                d["age"] = est.age(node.id)
        return d

    def visible_nodes(c: Ctx, cls: str) -> list:
        view = scoped_graph(c.est, c.pr)
        ids = {n["id"] for n in view["nodes"]}
        return [n for n in c.store.nodes(cls) if n.id in ids]

    def register_entity(path: str, cls: str) -> None:
        @api.get(f"/{path}", name=f"list_{path}")
        def list_items(c: Ctx = Depends(ctx)) -> list[dict]:
            c.audit(f"{path}.list")
            return [item_view(c, n) for n in visible_nodes(c, cls)]

        @api.get(f"/{path}/{{node_id}}", name=f"get_{path}")
        def get_item(node_id: str, c: Ctx = Depends(ctx)) -> dict:
            node = c.store.get_node(node_id)
            if node.cls != cls:
                raise NotFound(node_id)
            if cls in ("Asset", "Liability"):
                require_item(c.est, c.pr, node_id)
            elif node_id not in {n.id for n in visible_nodes(c, cls)}:
                raise AccessDenied(f"{c.pr.role} cannot access {node_id}")
            c.audit(f"{path}.view", node_id)
            return item_view(c, node)

        @api.post(f"/{path}", name=f"create_{path}", status_code=201)
        def create_item(body: NodeIn, c: Ctx = Depends(ctx)) -> dict:
            require_write(c.pr)
            node = c.store.add_node(cls, body.props, human(f"api:{c.pr.actor}"), node_id=body.id)
            c.audit(f"{path}.created", node.id)
            return item_view(c, node)

        @api.patch(f"/{path}/{{node_id}}", name=f"update_{path}")
        def update_item(node_id: str, body: PatchIn, c: Ctx = Depends(ctx)) -> dict:
            require_write(c.pr)
            if c.store.get_node(node_id).cls != cls:
                raise NotFound(node_id)
            node = c.store.update_node(node_id, body.props, human(f"api:{c.pr.actor}"))
            c.audit(f"{path}.updated", node_id, {"fields": sorted(body.props)})
            return item_view(c, node)

        @api.delete(f"/{path}/{{node_id}}", name=f"delete_{path}")
        def delete_item(node_id: str, c: Ctx = Depends(ctx)) -> dict:
            require_write(c.pr)
            if c.store.get_node(node_id).cls != cls:
                raise NotFound(node_id)
            c.store.delete_node(node_id)
            c.audit(f"{path}.deleted", node_id)
            return {"ok": True}

    for path, cls in ENTITIES.items():
        register_entity(path, cls)

    @api.post("/relations", status_code=201)
    def add_relation(body: RelationIn, c: Ctx = Depends(ctx)) -> dict:
        require_write(c.pr)
        e = c.store.add_edge(body.src, body.rel, body.dst, human(f"api:{c.pr.actor}"), body.props)
        c.audit("relation.created", e.id)
        return e.to_dict()

    @api.delete("/relations/{edge_id:path}")
    def delete_relation(edge_id: str, c: Ctx = Depends(ctx)) -> dict:
        require_write(c.pr)
        c.store.delete_edge(edge_id)
        c.audit("relation.deleted", edge_id)
        return {"ok": True}

    # ------------------------------------------------------------------ analysis
    def gaps_for(c: Ctx):
        return detect_gaps(c.est, settings.expiry_window_days)

    @api.get("/gaps")
    def gaps(c: Ctx = Depends(ctx)) -> list[dict]:
        return [g.model_dump() for g in scoped_gaps(gaps_for(c), c.est, c.pr)]

    @api.get("/readiness")
    def get_readiness(c: Ctx = Depends(ctx)) -> dict:
        if c.pr.role not in ("owner", "spouse"):
            raise AccessDenied("readiness is visible to the owner and spouse")
        return readiness(gaps_for(c)).model_dump()

    @api.get("/graph")
    def graph(c: Ctx = Depends(ctx)) -> dict:
        view = scoped_graph(c.est, c.pr)
        gs = scoped_gaps(gaps_for(c), c.est, c.pr)
        by_node: dict[str, list[dict]] = {}
        for g in gs:
            for sid in g.subject_ids:
                if sid in view["visible_items"] or c.pr.role in ("owner", "spouse"):
                    by_node.setdefault(sid, []).append({"key": g.key, "severity": g.severity, "title": g.title})
        c.audit("graph.view")
        return view | {"gaps_by_node": by_node, "as_of": settings.as_of.isoformat()}

    def _checklist(c: Ctx, scenario: str, subject: str | None):
        if scenario not in SCENARIOS:
            raise HTTPException(404, f"unknown scenario; choose from {sorted(SCENARIOS)}")
        cl = generate(c.est, scenario, subject, gaps_for(c))
        if c.pr.role not in ("owner", "spouse") or c.pr.spouse_scope == "shared":
            items = visible_items(c.est, c.pr)
            cl.steps = [s for s in cl.steps if not s.item_ids or set(s.item_ids) & items]
            for i, s in enumerate(cl.steps, start=1):
                s.order = i
            cl.blocked_count = sum(s.blocked for s in cl.steps)
        c.audit("checklist.view", scenario)
        return cl

    @api.get("/checklist/{scenario}")
    def checklist(scenario: str, subject: str | None = None, c: Ctx = Depends(ctx)) -> dict:
        return _checklist(c, scenario, subject).model_dump()

    @api.get("/checklist/{scenario}/pdf")
    def checklist_pdf_route(scenario: str, subject: str | None = None, c: Ctx = Depends(ctx)) -> Response:
        cl = _checklist(c, scenario, subject)
        pdf = checklist_pdf(cl, c.store.meta.get("display_name", "Family"))
        return Response(pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="checklist-{scenario}.pdf"'})

    @api.get("/scenarios")
    def scenarios() -> dict:
        return SCENARIOS

    # ------------------------------------------------------------------ emergency access
    @api.get("/access-requests")
    def list_access(c: Ctx = Depends(ctx)) -> list[dict]:
        reqs = emergency.list_requests(c.store)
        if c.pr.role not in ("owner", "spouse"):
            reqs = [r for r in reqs if r.requester_id == c.pr.person_id]
        return [r.model_dump(mode="json") for r in reqs]

    @api.post("/access-requests", status_code=201)
    def create_access(body: AccessRequestIn, c: Ctx = Depends(ctx)) -> dict:
        requester = body.requester_id or c.pr.person_id
        if c.pr.role not in ("owner",) and requester != c.pr.person_id:
            raise AccessDenied("you can only request access for yourself")
        reason = check_free_text(body.reason or "Emergency", "reason")
        wait = settings.emergency_wait_hours if body.wait_hours is None else body.wait_hours
        return emergency.create_request(c.est, requester, reason, wait).model_dump(mode="json")

    @api.post("/access-requests/{rid}/cancel")
    def cancel_access(rid: str, c: Ctx = Depends(ctx)) -> dict:
        if c.pr.role != "owner":
            raise AccessDenied("only the owner can cancel an emergency-access request")
        try:
            return emergency.cancel_request(c.store, rid, c.pr.actor).model_dump(mode="json")
        except KeyError as e:
            raise NotFound(rid) from e

    @api.post("/access-requests/{rid}/approve-after-delay")
    def approve_access(rid: str, c: Ctx = Depends(ctx)) -> dict:
        try:
            req = emergency.get_request(c.store, rid)
        except KeyError as e:
            raise NotFound(rid) from e
        if c.pr.role != "owner" and req.requester_id != c.pr.person_id:
            raise AccessDenied("not your request")
        return emergency.activate_after_delay(c.store, rid).model_dump(mode="json")

    @api.get("/access-requests/{rid}/view")
    def emergency_view(rid: str, c: Ctx = Depends(ctx)) -> dict:
        try:
            req = emergency.get_request(c.store, rid)
        except KeyError as e:
            raise NotFound(rid) from e
        if req.status != "active":
            raise AccessDenied(f"emergency access is {req.status}")
        if c.pr.role != "owner" and req.requester_id != c.pr.person_id:
            raise AccessDenied("not your request")
        pr = Principal(role="emergency", person_id=req.requester_id, access_request_id=rid)
        audit.append(c.store, req.requester_id, "emergency", "emergency.view", rid)
        view = scoped_graph(c.est, pr)
        cl = generate(c.est, "death_of_earner", gaps=gaps_for(c))
        cl.steps = [s for s in cl.steps if not s.item_ids or set(s.item_ids) & set(view["visible_items"])]
        return {"request": req.model_dump(mode="json"), "graph": view, "checklist": cl.model_dump()}

    @api.get("/notifications")
    def notes(c: Ctx = Depends(ctx)) -> list[dict]:
        return emergency.notifications(c.store, c.pr.person_id or "")

    @api.get("/demo/clock")
    def clock(c: Ctx = Depends(ctx)) -> dict:
        return {"now": emergency.now(c.store).isoformat()}

    @api.post("/demo/clock/advance")
    def advance(body: ClockIn, c: Ctx = Depends(ctx)) -> dict:
        now = emergency.advance_clock(c.store, body.hours)
        c.audit("demo.clock_advanced", details={"hours": body.hours})
        return {"now": now.isoformat()}

    # ------------------------------------------------------------------ audit / export / import
    @api.get("/audit")
    def get_audit(limit: int = 200, c: Ctx = Depends(ctx)) -> dict:
        if c.pr.role != "owner":
            raise AccessDenied("only the owner can read the audit log")
        ok, bad = audit.verify(c.store)
        return {"chain_valid": ok, "first_bad_seq": bad, "entries": audit.entries(c.store, limit)}

    @api.post("/export")
    def export(body: ExportIn, c: Ctx = Depends(ctx)) -> Response:
        if c.pr.role != "owner":
            raise AccessDenied("only the owner can export the vault")
        blob = encrypt_export(c.store.dump(), body.passphrase)
        c.audit("vault.exported")
        fid = c.session.family_id
        return Response(blob, media_type="application/octet-stream",
                        headers={"Content-Disposition": f'attachment; filename="{fid}.fvault"'})

    @api.post("/import", status_code=201)
    def import_vault(body: ImportIn) -> dict:
        try:
            data = decrypt_export(base64.b64decode(body.blob_b64), body.export_passphrase)
        except (WrongPassphrase, TamperDetected) as e:
            raise HTTPException(400, f"could not import: {e}") from e
        except (CryptoError, ValueError) as e:
            raise HTTPException(400, "could not import: not a family-vault export") from e
        fid, store = reg.create(body.display_name, body.new_vault_passphrase)
        store.load_dump(data)
        store.set_meta(data.get("meta", {}) | {"id": fid, "display_name": body.display_name})
        audit.append(store, "owner", "owner", "vault.imported", fid)
        s = reg.new_session(fid, Principal(role="owner", person_id=store.meta.get("owner")))
        return session_out(s)

    # ------------------------------------------------------------------ onboarding
    @api.get("/onboarding")
    def onboarding_state(c: Ctx = Depends(ctx)) -> dict:
        require_write(c.pr)
        return onboarding.current(c.est).model_dump()

    @api.post("/onboarding/answer")
    def onboarding_answer(body: dict, c: Ctx = Depends(ctx)) -> dict:
        require_write(c.pr)
        try:
            res = onboarding.answer(c.est, body)
        except (MaskingError, OntologyError, NotFound):
            raise
        except (KeyError, ValueError) as e:
            raise HTTPException(422, f"could not save that answer: {e}") from e
        c.audit("onboarding.answer", res.question.section, {"created": res.last_created})
        return res.model_dump()

    @api.post("/onboarding/reset")
    def onboarding_reset(c: Ctx = Depends(ctx)) -> dict:
        require_write(c.pr)
        onboarding.reset(c.store)
        return onboarding.current(c.est).model_dump()

    @api.get("/masking-policy")
    def masking_policy() -> dict:
        return {"why": WHY, "accepted_examples": ["1234", "XXXX1234", "****1234"],
                "rejected_examples": ["full account numbers", "Aadhaar / PAN", "card numbers", "passwords / PIN / OTP"]}

    return api


app = create_app()
