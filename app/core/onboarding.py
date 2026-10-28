"""Guided onboarding: a deterministic slot-filling state machine.

The conversation is driven by this engine, not by the LLM. Each question has a structured input
(text, yes/no, person form, asset form) so answers can be validated by the same ontology + masking
guard as the API. The LLM (if live) only rephrases the question text from structural context.
Every section is skippable; progress = sections completed / total.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.core.estate import Estate
from app.core.gaps import TYPE_LABELS
from app.kg.llm import StructuralContext, get_llm
from app.kg.provenance import human

PROV_SOURCE = "onboarding"
ASSET_SECTIONS = ["insurance", "bank_account", "fixed_deposit", "demat", "mutual_fund", "property", "vehicle"]
SECTIONS = ["household", *ASSET_SECTIONS, "liabilities", "review"]
DEFAULT_DOC = {"insurance": "policy_document", "bank_account": "passbook", "fixed_deposit": "fd_receipt",
               "demat": "demat_holding_statement", "mutual_fund": "cas_statement", "property": "title_deed",
               "vehicle": "rc_book"}
DEFAULT_INST_KIND = {"insurance": "insurer", "bank_account": "bank", "fixed_deposit": "bank",
                     "demat": "depository_participant", "mutual_fund": "amc", "property": "sub_registrar",
                     "vehicle": "rto", "liabilities": "bank"}
SECTION_TITLES = {"household": "Your family", "insurance": "Insurance", "bank_account": "Bank accounts",
                  "fixed_deposit": "Fixed deposits", "demat": "Shares (demat)", "mutual_fund": "Mutual funds",
                  "property": "Property", "vehicle": "Vehicles", "liabilities": "Loans", "review": "Review"}

TEMPLATES = {
    "owner": "Let's start with you. What is your name, and your date of birth?",
    "member": "Who else is in your family? Add one person at a time, or say you're done.",
    "has": "Do you or anyone in the family have a {type}?",
    "item": "Tell me about the {type}. Only the last 4 digits of any number, please.",
    "another": "Got it. Is there another {type} to add?",
    "has_liabilities": "Does anyone in the family have a loan?",
    "item_liabilities": "Tell me about the loan. Only the last 4 digits of any number, please.",
    "another_liabilities": "Got it. Is there another loan to add?",
    "review": "All done! Have a look at the gaps we found and your family readiness score.",
}


class Question(BaseModel):
    id: str
    section: str
    section_title: str
    prompt: str
    input: str  # person_form | yesno | asset_form | liability_form | done
    skippable: bool = True
    context: dict[str, Any] = {}


class OnboardingState(BaseModel):
    id: str = "state"
    section_idx: int = 0
    stage: str = "start"  # start | has | item | another
    skipped: list[str] = []
    created: list[str] = []


class OnboardingResult(BaseModel):
    question: Question
    progress: dict
    last_created: list[str] = []
    message: str = ""


def _load(store) -> OnboardingState:
    rows = {r["id"]: r for r in store.get_records("onboarding")}
    return OnboardingState.model_validate(rows["state"]) if "state" in rows else OnboardingState()


def _save(store, st: OnboardingState) -> None:
    store.put_record("onboarding", "state", st.model_dump())


def _phrase(section: str, slot: str, template: str, est: Estate) -> str:
    ctx = StructuralContext(task="onboarding_question", fields={
        "template": template, "section": section, "slot": slot,
        "people_count": len(est.people()), "assets_count": len(est.assets())})
    return get_llm().rephrase(ctx)


def _question(est: Estate, st: OnboardingState) -> Question:
    section = SECTIONS[st.section_idx]
    title = SECTION_TITLES[section]
    people = [{"id": p.id, "name": p.props["name"]} for p in est.people() if p.props.get("is_alive", True)]
    if section == "household":
        owner_exists = bool((est.store.meta or {}).get("owner"))
        slot = "member" if owner_exists else "owner"
        return Question(id=f"household.{slot}", section=section, section_title=title, input="person_form",
                        prompt=_phrase(section, slot, TEMPLATES[slot], est), skippable=owner_exists,
                        context={"people": people, "ask_relation": owner_exists})
    if section == "review":
        return Question(id="review", section=section, section_title=title, input="done", skippable=False,
                        prompt=_phrase(section, "review", TEMPLATES["review"], est))
    is_li = section == "liabilities"
    stage = "has" if st.stage == "start" else st.stage
    key = f"{stage}_liabilities" if is_li else stage
    tmpl = TEMPLATES[key].replace("{type}", TYPE_LABELS.get(section, "loan"))
    kind = {"has": "yesno", "another": "yesno"}.get(stage, "liability_form" if is_li else "asset_form")
    ctx: dict[str, Any] = {"people": people}
    if kind.endswith("form"):
        ctx |= {"asset_type": section, "default_doc_type": DEFAULT_DOC.get(section, "loan_agreement"),
                "institution_kind": DEFAULT_INST_KIND[section]}
    return Question(id=f"{section}.{stage}", section=section, section_title=title, input=kind,
                    prompt=_phrase(section, stage, tmpl, est), context=ctx)


def progress(st: OnboardingState) -> dict:
    total = len(SECTIONS) - 1
    done = min(st.section_idx, total)
    return {"done": done, "total": total, "percent": round(100 * done / total), "section": SECTIONS[st.section_idx],
            "sections": [{"id": s, "title": SECTION_TITLES[s], "skipped": s in st.skipped} for s in SECTIONS[:-1]]}


def current(est: Estate) -> OnboardingResult:
    st = _load(est.store)
    return OnboardingResult(question=_question(est, st), progress=progress(st))


def _next_section(st: OnboardingState) -> None:
    st.section_idx = min(st.section_idx + 1, len(SECTIONS) - 1)
    st.stage = "start"


def _institution(est: Estate, name: str, kind: str) -> str:
    for n in est.store.nodes("Institution"):
        if n.props["name"].strip().lower() == name.strip().lower():
            return n.id
    return est.store.add_node("Institution", {"name": name, "kind": kind}, human(PROV_SOURCE)).id


def _create_item(est: Estate, section: str, a: dict) -> list[str]:
    """Create an asset/liability plus its links from a form answer. Validation errors propagate."""
    store, prov = est.store, human(PROV_SOURCE)
    is_li = section == "liabilities"
    props = {"label": a["label"]}
    if a.get("masked_id"):
        props["masked_id"] = a["masked_id"]
    if is_li:
        props |= {"liability_type": a.get("liability_type", "loan"), "subtype": a.get("subtype", "other")}
    else:
        props["asset_type"] = section
        for f in ("maturity_date", "expiry_date"):
            if a.get(f):
                props[f] = a[f]
    # Validate everything before writing anything.
    store.onto.validate_node("Liability" if is_li else "Asset", props)
    if a.get("document_location"):
        store.onto.validate_node("Document", {"doc_type": "other", "label": "x", "location": a["document_location"]})
    for pid in [*(a.get("owners") or []), *(a.get("co_owners") or []), *(a.get("nominees") or []),
                *(a.get("knows") or [])]:
        if est.node(pid).cls != "Person":
            raise ValueError(f"{pid} is not a person")
    created = []
    item = store.add_node("Liability" if is_li else "Asset", props, prov)
    created.append(item.id)
    for pid in a.get("owners") or [store.meta.get("owner")]:
        if pid:
            store.add_edge(pid, "owns", item.id, prov, {"role": "owner"})
    for pid in a.get("co_owners") or []:
        store.add_edge(pid, "owns", item.id, prov, {"role": "co_borrower" if is_li else "joint"})
    if not is_li:
        for pid in a.get("nominees") or []:
            store.add_edge(pid, "nominee_of", item.id, prov)
    for pid in a.get("knows") or []:
        store.add_edge(pid, "knows_about", item.id, prov)
    if a.get("institution_name"):
        store.add_edge(item.id, "held_at", _institution(est, a["institution_name"], DEFAULT_INST_KIND[section]), prov)
    if a.get("has_document"):
        doc_type = a.get("doc_type") or DEFAULT_DOC.get(section, "loan_agreement")
        d = store.add_node("Document", {"doc_type": doc_type, "label": a.get("document_label") or "Papers",
                                        "location": a.get("document_location")}, prov)
        store.add_edge(item.id, "documented_by", d.id, prov)
        created.append(d.id)
    return created


def answer(est: Estate, ans: dict) -> OnboardingResult:
    store = est.store
    st = _load(store)
    section = SECTIONS[st.section_idx]
    created: list[str] = []
    msg = ""
    if ans.get("skip"):
        if section == "household" and not store.meta.get("owner"):
            raise ValueError("please tell us your name first; it can't be skipped")
        st.skipped.append(section)
        _next_section(st)
    elif section == "household":
        if ans.get("done"):
            _next_section(st)
        else:
            owner = store.meta.get("owner")
            props = {"name": ans["name"], "relation": "self" if not owner else ans.get("relation", "other")}
            if ans.get("dob"):
                props["dob"] = ans["dob"]
            if not owner:
                props["is_earner"] = bool(ans.get("is_earner", True))
            p = store.add_node("Person", props, human(PROV_SOURCE))
            created.append(p.id)
            if not owner:
                store.set_meta(store.meta | {"owner": p.id, "primary_earner": p.id})
            msg = f"Added {p.props['name']}."
    elif section == "review":
        msg = "Onboarding is complete."
    elif st.stage in ("start", "has", "another"):
        if ans.get("yes"):
            st.stage = "item"
        else:
            _next_section(st)
    else:  # item form
        created = _create_item(est, section, ans)
        st.stage = "another"
        msg = "Saved."
    st.created += created
    _save(store, st)
    return OnboardingResult(question=_question(est, st), progress=progress(st), last_created=created, message=msg)


def reset(store) -> None:
    _save(store, OnboardingState())
