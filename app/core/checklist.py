"""'If something happens' checklist generator (deterministic).

For a scenario and a subject person it produces an ordered list of steps: universal steps first,
then one step per affected asset/liability grouped by institution, each with required documents,
who in the family should act, and what is blocked by open gaps. Wording may be polished by the
LLM (structural templates only); the content never depends on it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.core.estate import Estate
from app.core.gaps import DOC_LABELS, Gap, detect_gaps
from app.kg.llm import StructuralContext, fill, get_llm

Scenario = Literal["death_of_earner", "incapacity", "loss_of_documents"]
SCENARIOS: dict[str, str] = {
    "death_of_earner": "Death of the earning member",
    "incapacity": "Serious illness or incapacity",
    "loss_of_documents": "Loss of documents (fire, flood, theft)",
}
DISCLAIMER = ("General guidance only — procedures differ by institution and state. Verify each step with the "
              "institution or a qualified professional before acting.")

TYPE_ORDER = {"insurance": 1, "bank_account": 2, "fixed_deposit": 3, "demat": 4, "mutual_fund": 5,
              "property": 6, "vehicle": 7, "other": 8, "loan": 9, "credit_card": 10}
HEIR_RELATIONS = ["spouse", "son", "daughter", "mother", "father"]

# (scenario, item type) -> (action code, template, documents)
DEATH = {
    "insurance": ("claim_death_benefit", "Tell {institution} about the death and file the death claim for {item}.",
                  ["Death certificate", "Policy document", "Claim form", "Claimant's ID and bank proof (KYC)"]),
    "bank_account": ("transmit_bank_account", "Ask {institution} to pay the balance of {item} to the nominee or "
                     "survivor.", ["Death certificate", "Passbook or statement", "Claim form", "Claimant's KYC"]),
    "fixed_deposit": ("claim_fixed_deposit", "Claim the fixed deposit {item} at {institution}.",
                      ["Death certificate", "FD receipt", "Claim form", "Claimant's KYC"]),
    "demat": ("transmit_demat", "Ask {institution} to move the shares in {item} to the claimant's demat account.",
              ["Death certificate", "Transmission request form", "Holding statement", "Claimant's client master"]),
    "mutual_fund": ("transmit_mutual_fund", "Request transmission of the units in {item} through {institution} or "
                    "its registrar.", ["Death certificate", "Transmission form", "CAS statement", "Claimant's KYC"]),
    "property": ("transfer_property", "Update the ownership records of {item} (mutation) at {institution}.",
                 ["Death certificate", "Title deed", "Will or succession / legal heir certificate"]),
    "vehicle": ("transfer_vehicle", "Transfer the registration of {item} at {institution}.",
                ["Death certificate", "Vehicle RC", "Transfer form", "Claimant's ID"]),
    "other": ("inform_institution", "Inform {institution} and ask how to claim {item}.",
              ["Death certificate", "Any account papers"]),
    "loan": ("inform_lender", "Inform {institution} about {item} and ask whether loan insurance covers what is "
             "outstanding.", ["Death certificate", "Loan agreement", "Loan insurance cover note (if any)"]),
    "credit_card": ("close_credit_card", "Inform {institution} and ask them to close {item}.",
                    ["Death certificate", "Latest card statement"]),
}
INCAPACITY = {
    "insurance": ("check_disability_benefits", "Ask {institution} whether {item} has disability or critical-illness "
                  "benefits, and keep premiums paid.", ["Doctor's certificate", "Policy document"]),
    "bank_account": ("arrange_account_operation", "Ask {institution} how a family member can operate {item} (joint "
                     "holder, mandate or power of attorney).", ["Doctor's certificate", "Passbook or statement",
                                                                "Power of attorney (if any)"]),
    "fixed_deposit": ("arrange_account_operation", "Ask {institution} how the family can renew or withdraw {item} "
                      "on the holder's behalf.", ["Doctor's certificate", "FD receipt", "Power of attorney (if any)"]),
    "demat": ("review_investments", "Ask {institution} what is needed for someone to manage {item} (usually a power "
              "of attorney).", ["Doctor's certificate", "Holding statement", "Power of attorney (if any)"]),
    "mutual_fund": ("review_investments", "Check whether SIPs in {item} should continue; changes usually need a "
                    "power of attorney.", ["CAS statement", "Power of attorney (if any)"]),
    "property": ("protect_property", "Keep {item} safe and taxes paid; it cannot be sold without a power of attorney "
                 "or court guardianship.", ["Title deed", "Property tax receipts"]),
    "vehicle": ("maintain_vehicle", "Keep the insurance of {item} renewed.", ["Vehicle RC", "Insurance policy"]),
    "other": ("check_with_institution", "Ask {institution} what the family can do for {item}.", ["Account papers"]),
    "loan": ("inform_lender", "Inform {institution}, ask about disability cover on {item}, and arrange EMIs.",
             ["Doctor's certificate", "Loan agreement", "Loan insurance cover note (if any)"]),
    "credit_card": ("limit_credit_card", "Ask {institution} to block or limit {item} if nobody can manage it.",
                    ["Latest card statement"]),
}
LOSS = ("request_duplicate", "Ask {institution} for a duplicate of the papers for {item}.",
        ["Lost-document report (police / online)", "Holder's ID proof", "Indemnity letter if asked"])

UNIVERSAL = {
    "death_of_earner": [
        ("obtain_death_certificate", "Get at least ten certified copies of the death certificate from the "
         "municipal office.", ["Hospital or cremation record", "Deceased's ID copy"]),
        ("locate_will_and_papers", "Find the will (if any) and gather the papers listed in the steps below.",
         ["Will (if any)"]),
    ],
    "incapacity": [
        ("medical_certificate", "Get a doctor's certificate describing the condition.", ["Hospital records"]),
        ("check_power_of_attorney", "Check whether a power of attorney exists. If not, ask a lawyer about "
         "guardianship.", ["Power of attorney (if any)"]),
    ],
    "loss_of_documents": [
        ("report_loss", "Report the lost documents to the police (many states allow this online).", ["Holder's ID"]),
        ("check_digital_copies", "Check DigiLocker and email for digital copies before asking for duplicates.", []),
    ],
}

BLOCKING_RULES = {
    "death_of_earner": {"G01", "G03", "G05", "G06", "G07"},
    "incapacity": {"G05", "G06"},
    "loss_of_documents": {"G05"},
}
BLOCK_REASON = {
    "G01": "No nominee: the institution may ask for a succession or legal heir certificate.",
    "G03": "Minor nominee with no guardian: money may be held until a guardian is appointed.",
    "G05": "Papers not recorded: you may need to request copies first.",
    "G06": "Only {who} knew about this, so the family may not find it.",
    "G07": "The nominee cannot act: expect a legal heir certificate or longer process.",
}


class Step(BaseModel):
    order: int
    action: str
    text: str
    institution: str | None = None
    institution_id: str | None = None
    item_ids: list[str] = []
    required_documents: list[str]
    actor_ids: list[str]
    actors: list[str]
    blocked: bool = False
    blocked_by: list[str] = []
    notes: list[str] = []


class Checklist(BaseModel):
    scenario: str
    scenario_label: str
    subject_id: str
    subject_name: str
    disclaimer: str = DISCLAIMER
    steps: list[Step]
    blocked_count: int


def next_of_kin(est: Estate, subject: str) -> list[str]:
    """Living adult household members who would usually act, in priority order."""
    owner = (getattr(est.store, "meta", {}) or {}).get("owner")
    people = [p for p in est.people() if p.id != subject and p.props.get("is_alive", True)
              and p.props.get("household", True) and not est.is_minor(p.id)]
    if subject == owner:
        ranked = [p for p in people if p.props.get("relation") in HEIR_RELATIONS]
        ranked.sort(key=lambda p: (HEIR_RELATIONS.index(p.props["relation"]), p.id))
        if ranked:
            return [p.id for p in ranked[:2]]
    people.sort(key=lambda p: (p.id != owner, p.id))
    return [p.id for p in people[:2]]


def _available(est: Estate, pid: str) -> bool:
    p = est.node(pid).props
    return p.get("is_alive", True) and p.get("reachable", True)


def resolve_actors(est: Estate, scenario: str, subject: str, item_id: str) -> tuple[list[str], list[str]]:
    """Return (actor ids, display labels)."""
    is_asset = est.node(item_id).cls == "Asset"
    co_owners = [o for o in est.owners(item_id) if o != subject and _available(est, o)]
    if scenario == "loss_of_documents":
        owners = [o for o in est.owners(item_id) if _available(est, o)]
        ids = owners or next_of_kin(est, subject)
        return ids, [est.name(i) for i in ids]
    if scenario == "death_of_earner" and is_asset:
        ids, labels = [], []
        for n in est.nominees(item_id):
            if not _available(est, n):
                continue
            if est.is_minor(n):
                for g in est.guardians(n):
                    ids.append(g)
                    labels.append(f"{est.name(g)} (guardian of {est.name(n)})")
            else:
                ids.append(n)
                labels.append(est.name(n))
        if ids:
            return ids, labels
    if co_owners:
        return co_owners, [est.name(i) for i in co_owners]
    ids = next_of_kin(est, subject)
    return ids, [est.name(i) for i in ids]


def _items_in_scope(est: Estate, scenario: str, subject: str) -> list[str]:
    if scenario == "loss_of_documents":
        items = [n.id for n in est.assets() + est.liabilities() if subject in est.owners(n.id)
                 or subject == (getattr(est.store, "meta", {}) or {}).get("owner")]
    else:
        items = [i for i in est.owned_by(subject)]

    def key(i: str):
        n = est.node(i)
        t = n.props.get("asset_type") or n.props.get("liability_type")
        inst = est.institution(i)
        return TYPE_ORDER.get(t, 99), inst.props["name"] if inst else "~", i

    return sorted(set(items), key=key)


def _phrase(scenario: str, action: str, template: str, item_type: str = "") -> str:
    ctx = StructuralContext(task="checklist_step", fields={"template": template, "scenario": scenario,
                                                           "action": action, "asset_type": item_type})
    return get_llm().rephrase(ctx)


def generate(est: Estate, scenario: str, subject: str | None = None, gaps: list[Gap] | None = None) -> Checklist:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}; choose from {sorted(SCENARIOS)}")
    subject = subject or est.earner()
    if not subject:
        raise ValueError("no subject person given and no earner recorded")
    est.node(subject)
    gaps = gaps if gaps is not None else detect_gaps(est)
    by_item: dict[str, list[Gap]] = {}
    for g in gaps:
        for sid in g.subject_ids:
            by_item.setdefault(sid, []).append(g)

    steps: list[Step] = []
    kin = next_of_kin(est, subject) if scenario != "loss_of_documents" else [subject]
    for action, template, docs in UNIVERSAL[scenario]:
        steps.append(Step(order=0, action=action, text=_phrase(scenario, action, template), required_documents=docs,
                          actor_ids=kin, actors=[est.name(i) for i in kin]))
    if scenario == "death_of_earner" and not any(
        d.props["doc_type"] == "will" for d in est.store.nodes("Document")
    ):
        steps[-1].notes.append("No will is recorded in the vault.")

    for item_id in _items_in_scope(est, scenario, subject):
        node = est.node(item_id)
        itype = node.props.get("asset_type") or node.props.get("liability_type")
        if scenario == "loss_of_documents":
            if not est.documents(item_id) and itype in ("other", "credit_card"):
                continue
            action, template, docs = LOSS
            have = [DOC_LABELS.get(d.props["doc_type"], d.props["label"]) for d in est.documents(item_id)]
            docs = docs + [f"Copy/number of: {h}" for h in have]
        else:
            action, template, docs = (DEATH if scenario == "death_of_earner" else INCAPACITY)[itype]
        inst = est.institution(item_id)
        inst_name = inst.props["name"] if inst else "the institution"
        text = fill(_phrase(scenario, action, template, itype), institution=inst_name,
                    item=f"\"{node.props['label']}\"")
        actor_ids, actor_labels = resolve_actors(est, scenario, subject, item_id)

        blocked_by, notes = [], []
        for g in by_item.get(item_id, []):
            if g.rule not in BLOCKING_RULES[scenario]:
                if g.rule == "G04":
                    notes.append(g.message)
                continue
            if g.rule == "G06":
                knowers = est.knowers(item_id)
                if scenario in ("death_of_earner", "incapacity") and knowers and knowers != [subject]:
                    continue  # someone else alive already knows
                who = est.name(knowers[0]) if knowers else "nobody"
                notes.append(BLOCK_REASON["G06"].format(who=who))
            else:
                notes.append(BLOCK_REASON[g.rule])
            blocked_by.append(g.key)
        # Minor-nominee gaps are keyed on the person; attach them to the asset step too.
        if scenario == "death_of_earner":
            for n in est.nominees(item_id):
                for g in by_item.get(n, []):
                    if g.rule == "G03" and g.key not in blocked_by:
                        blocked_by.append(g.key)
                        notes.append(BLOCK_REASON["G03"])
        steps.append(Step(
            order=0, action=action, text=text, institution=inst_name if inst else None,
            institution_id=inst.id if inst else None, item_ids=[item_id], required_documents=docs,
            actor_ids=actor_ids, actors=actor_labels or ["A family member"], blocked=bool(blocked_by),
            blocked_by=sorted(blocked_by), notes=notes,
        ))

    for i, s in enumerate(steps, start=1):
        s.order = i
    return Checklist(scenario=scenario, scenario_label=SCENARIOS[scenario], subject_id=subject,
                     subject_name=est.name(subject), steps=steps, blocked_count=sum(s.blocked for s in steps))
