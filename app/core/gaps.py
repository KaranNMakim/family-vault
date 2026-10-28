"""Deterministic gap-detection rules (no LLM).

Each rule yields Gap objects with a stable key ``<rule>:<subject>``, a severity, a plain-language
message and fix, and a ``fix_action`` the UI can turn into a one-click shortcut.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterator
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from app.core.estate import ANY_OF_TYPES, NOMINATION_TYPES, REQUIRED_DOCS, Estate

Severity = Literal["critical", "high", "medium", "low", "info"]
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

DOC_LABELS = {
    "policy_document": "policy document / bond", "fd_receipt": "FD receipt or advice", "passbook": "passbook",
    "bank_statement": "bank statement", "demat_holding_statement": "demat holding statement",
    "cas_statement": "consolidated account statement (CAS)", "title_deed": "title / sale deed",
    "rc_book": "vehicle RC", "loan_cover_note": "loan insurance cover note",
}
TYPE_LABELS = {
    "insurance": "insurance policy", "fixed_deposit": "fixed deposit", "bank_account": "bank account",
    "demat": "demat account", "mutual_fund": "mutual fund folio", "property": "property", "vehicle": "vehicle",
    "other": "asset",
}


class Gap(BaseModel):
    key: str
    rule: str
    title: str
    category: Literal["nominees", "guardianship", "documents", "knowledge", "deadlines", "liabilities"]
    severity: Severity
    subject_ids: list[str]
    message: str
    fix: str
    fix_action: dict = Field(default_factory=dict)


RuleFn = Callable[[Estate, int], Iterator[Gap]]
RULES: dict[str, tuple[str, RuleFn]] = {}


def rule(rule_id: str, name: str):
    def deco(fn: RuleFn) -> RuleFn:
        RULES[rule_id] = (name, fn)
        return fn

    return deco


def _where(est: Estate, item_id: str) -> str:
    inst = est.institution(item_id)
    return inst.props["name"] if inst else "the institution"


@rule("G01", "asset_without_nominee")
def no_nominee(est: Estate, window: int) -> Iterator[Gap]:
    for a in est.assets():
        if a.props["asset_type"] in NOMINATION_TYPES and not est.nominees(a.id):
            owner = ", ".join(est.name(o) for o in est.owners(a.id)) or "the owner"
            yield Gap(
                key=f"G01:{a.id}", rule="G01", title="No nominee recorded", category="nominees", severity="high",
                subject_ids=[a.id],
                message=f"{owner}'s {TYPE_LABELS[a.props['asset_type']]} \"{a.props['label']}\" at "
                        f"{_where(est, a.id)} has no nominee.",
                fix=f"Add a nominee with {_where(est, a.id)}. Most banks and insurers let you do this online or "
                    "with a one-page nomination form. Without one, the family may need a succession certificate.",
                fix_action={"kind": "add_nominee", "asset_id": a.id},
            )


@rule("G02", "nominee_mismatch")
def nominee_mismatch(est: Estate, window: int) -> Iterator[Gap]:
    for p in est.people():
        groups: dict[frozenset, list[str]] = defaultdict(list)
        for aid in est.owned_by(p.id):
            if est.node(aid).cls != "Asset" or est.owners(aid) != [p.id]:
                continue  # only sole holdings; joint holdings follow survivorship rules
            noms = frozenset(est.nominees(aid))
            if noms:
                groups[noms].append(aid)
        if len(groups) > 1:
            parts = "; ".join(
                f"{', '.join(sorted(est.name(n) for n in noms))} on "
                f"{', '.join(est.node(a).props['label'] for a in sorted(aids))}"
                for noms, aids in sorted(groups.items(), key=lambda kv: sorted(kv[1]))
            )
            yield Gap(
                key=f"G02:{p.id}", rule="G02", title="Different nominees across holdings", category="nominees",
                severity="medium", subject_ids=[p.id] + sorted(a for aids in groups.values() for a in aids),
                message=f"{p.props['name']}'s holdings name different nominees: {parts}.",
                fix="Check this is intentional. If not, update the nominations so they match your wishes "
                    "(and your will, if you have one) — mismatches are a common cause of family disputes.",
                fix_action={"kind": "review_nominees", "person_id": p.id},
            )


@rule("G03", "minor_nominee_without_guardian")
def minor_nominee(est: Estate, window: int) -> Iterator[Gap]:
    for p in est.people():
        aids = est.nominated_assets(p.id)
        if aids and est.is_minor(p.id) and not est.guardians(p.id):
            labels = ", ".join(est.node(a).props["label"] for a in sorted(aids))
            yield Gap(
                key=f"G03:{p.id}", rule="G03", title="Minor nominee has no guardian / appointee",
                category="guardianship", severity="critical", subject_ids=[p.id] + sorted(aids),
                message=f"{p.props['name']} (age {est.age(p.id)}) is nominee on {labels}, but no guardian "
                        "or appointee is recorded.",
                fix="Name an appointee/guardian with each institution (insurers ask for an 'appointee' for minor "
                    "nominees) and record the guardian here. Otherwise money may be held until the child turns 18.",
                fix_action={"kind": "add_guardian", "person_id": p.id},
            )


@rule("G04", "maturing_or_expiring_soon")
def maturing(est: Estate, window: int) -> Iterator[Gap]:
    lo, hi = est.as_of - timedelta(days=90), est.as_of + timedelta(days=window)
    for a in est.assets():
        if a.props["asset_type"] not in {"fixed_deposit", "insurance"}:
            continue
        for field, verb in (("maturity_date", "matures"), ("expiry_date", "expires")):
            raw = a.props.get(field)
            if not raw:
                continue
            d = date.fromisoformat(raw)
            if not lo <= d <= hi:
                continue
            days = (d - est.as_of).days
            when = f"in {days} days ({raw})" if days >= 0 else f"{-days} days ago ({raw}) — check it was claimed"
            yield Gap(
                key=f"G04:{a.id}", rule="G04", title=f"{TYPE_LABELS[a.props['asset_type']].capitalize()} {verb} soon"
                if days >= 0 else "Matured — possibly unclaimed",
                category="deadlines", severity="high" if days <= 30 else "medium", subject_ids=[a.id],
                message=f"\"{a.props['label']}\" at {_where(est, a.id)} {verb} {when}.",
                fix="Decide now whether to renew, reinvest or claim, and tell the family where the proceeds go. "
                    "Unclaimed deposits eventually move to the RBI/IEPF unclaimed funds.",
                fix_action={"kind": "review_date", "asset_id": a.id},
            )
            break


@rule("G05", "missing_supporting_document")
def missing_document(est: Estate, window: int) -> Iterator[Gap]:
    for a in est.assets():
        required = REQUIRED_DOCS.get(a.props["asset_type"], set())
        if not required:
            continue
        have = {d.props["doc_type"] for d in est.documents(a.id)}
        missing = (set() if have & required else required) if a.props["asset_type"] in ANY_OF_TYPES \
            else required - have
        if missing:
            names = " or ".join(DOC_LABELS[m] for m in sorted(missing))
            yield Gap(
                key=f"G05:{a.id}", rule="G05", title="Supporting document not recorded", category="documents",
                severity="high" if a.props["asset_type"] == "property" else "medium", subject_ids=[a.id],
                message=f"No {names} is recorded for \"{a.props['label']}\".",
                fix=f"Find the {names} (or download a copy from {_where(est, a.id)}) and note where it is kept.",
                fix_action={"kind": "add_document", "asset_id": a.id, "doc_types": sorted(missing)},
            )


@rule("G06", "single_point_of_knowledge")
def single_knowledge(est: Estate, window: int) -> Iterator[Gap]:
    for a in est.assets():
        knowers = est.knowers(a.id)
        if len(knowers) <= 1:
            who = est.name(knowers[0]) if knowers else "nobody in the family"
            yield Gap(
                key=f"G06:{a.id}", rule="G06", title="Only one person knows this exists", category="knowledge",
                severity="high", subject_ids=[a.id] + knowers,
                message=f"Only {who} knows about \"{a.props['label']}\" at {_where(est, a.id)}.",
                fix="Tell at least one other trusted family member that it exists and where its papers are, "
                    "then mark them here as someone who knows.",
                fix_action={"kind": "share_knowledge", "asset_id": a.id},
            )


@rule("G07", "nominee_deceased_or_unreachable")
def nominee_unavailable(est: Estate, window: int) -> Iterator[Gap]:
    for e in est.store.edges(rel="nominee_of"):
        p = est.node(e.src).props
        dead, unreachable = not p.get("is_alive", True), not p.get("reachable", True)
        if dead or unreachable:
            a = est.node(e.dst).props
            state = "has passed away" if dead else "cannot currently be reached"
            yield Gap(
                key=f"G07:{e.dst}/{e.src}", rule="G07", title="Nominee " + ("has died" if dead else "unreachable"),
                category="nominees", severity="critical" if dead else "high", subject_ids=[e.dst, e.src],
                message=f"The nominee on \"{a['label']}\", {p['name']}, {state}.",
                fix=f"Update the nomination with {_where(est, e.dst)} to someone who can act for the family.",
                fix_action={"kind": "replace_nominee", "asset_id": e.dst, "person_id": e.src},
            )


@rule("G08", "liability_without_cover")
def liability_cover(est: Estate, window: int) -> Iterator[Gap]:
    for li in est.liabilities():
        if li.props["liability_type"] != "loan":
            continue
        borrowers = est.owners(li.id)
        covered = any(d.props["doc_type"] == "loan_cover_note" for d in est.documents(li.id))
        if len(borrowers) <= 1 and not covered:
            yield Gap(
                key=f"G08:{li.id}", rule="G08", title="Loan has no co-borrower or cover note", category="liabilities",
                severity="info", subject_ids=[li.id] + borrowers,
                message=f"\"{li.props['label']}\" has a single borrower and no loan-insurance cover note recorded.",
                fix="For information: check whether the loan has credit-life cover. If not, the family may have to "
                    "keep paying EMIs. Record the cover note here if one exists.",
                fix_action={"kind": "add_document", "asset_id": li.id, "doc_types": ["loan_cover_note"]},
            )


def detect_gaps(est: Estate, window_days: int = 60) -> list[Gap]:
    gaps = [g for _, (_, fn) in sorted(RULES.items()) for g in fn(est, window_days)]
    return sorted(gaps, key=lambda g: (SEVERITY_ORDER[g.severity], g.rule, g.key))
