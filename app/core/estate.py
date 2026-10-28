"""Read-only query helpers over a GraphStore, plus derived (rule-based) facts."""

from __future__ import annotations

from datetime import date

from app.kg.provenance import Provenance, rule
from app.kg.store import GraphStore, Node

# Asset types where Indian institutions offer nomination in practice.
NOMINATION_TYPES = {"insurance", "fixed_deposit", "bank_account", "demat", "mutual_fund"}
# Supporting documents a family needs to make a claim, by asset type.
REQUIRED_DOCS: dict[str, set[str]] = {
    "insurance": {"policy_document"},
    "fixed_deposit": {"fd_receipt"},
    "bank_account": {"passbook", "bank_statement"},  # either one
    "demat": {"demat_holding_statement"},
    "mutual_fund": {"cas_statement"},
    "property": {"title_deed"},
    "vehicle": {"rc_book"},
    "other": set(),
}
# For bank accounts any one of the listed documents is enough.
ANY_OF_TYPES = {"bank_account"}


def age_on(dob: str | None, as_of: date) -> int | None:
    if not dob:
        return None
    b = date.fromisoformat(dob)
    return as_of.year - b.year - ((as_of.month, as_of.day) < (b.month, b.day))


class Estate:
    def __init__(self, store: GraphStore, as_of: date):
        self.store = store
        self.as_of = as_of

    # ------------------------------------------------------------------ basic lookups
    def node(self, nid: str) -> Node:
        return self.store.get_node(nid)

    def people(self) -> list[Node]:
        return self.store.nodes("Person")

    def assets(self) -> list[Node]:
        return self.store.nodes("Asset")

    def liabilities(self) -> list[Node]:
        return self.store.nodes("Liability")

    def name(self, nid: str) -> str:
        p = self.node(nid).props
        return p.get("name") or p.get("label") or nid

    def owners(self, item_id: str, roles: tuple[str, ...] = ("owner", "joint", "co_borrower")) -> list[str]:
        return [e.src for e in self.store.edges(rel="owns", dst=item_id) if e.props.get("role", "owner") in roles]

    def owned_by(self, person_id: str) -> list[str]:
        return [e.dst for e in self.store.edges(rel="owns", src=person_id)]

    def nominees(self, asset_id: str) -> list[str]:
        return [e.src for e in self.store.edges(rel="nominee_of", dst=asset_id)]

    def nominated_assets(self, person_id: str) -> list[str]:
        return [e.dst for e in self.store.edges(rel="nominee_of", src=person_id)]

    def guardians(self, person_id: str) -> list[str]:
        return [e.src for e in self.store.edges(rel="guardian_of", dst=person_id)]

    def institution(self, item_id: str) -> Node | None:
        e = self.store.edges(rel="held_at", src=item_id)
        return self.node(e[0].dst) if e else None

    def documents(self, item_id: str) -> list[Node]:
        return [self.node(e.dst) for e in self.store.edges(rel="documented_by", src=item_id)]

    def advisors(self, item_id: str) -> list[str]:
        return [e.dst for e in self.store.edges(rel="advised_by", src=item_id)]

    def advised_items(self, advisor_id: str) -> list[str]:
        return [e.src for e in self.store.edges(rel="advised_by", dst=advisor_id)]

    # ------------------------------------------------------------------ derived facts
    def is_alive(self, pid: str) -> bool:
        return self.node(pid).props.get("is_alive", True)

    def age(self, pid: str) -> int | None:
        return age_on(self.node(pid).props.get("dob"), self.as_of)

    def is_minor(self, pid: str) -> bool:
        a = self.age(pid)
        return a is not None and a < 18

    def knowers(self, item_id: str) -> list[str]:
        """Living household members who know the item exists (owners know implicitly)."""
        ids = set(self.owners(item_id)) | {e.src for e in self.store.edges(rel="knows_about", dst=item_id)}
        out = []
        for pid in sorted(ids):
            p = self.node(pid).props
            if p.get("is_alive", True) and p.get("household", True):
                out.append(pid)
        return out

    def earner(self) -> str | None:
        meta = getattr(self.store, "meta", {}) or {}
        if meta.get("primary_earner"):
            return meta["primary_earner"]
        earners = [p.id for p in self.people() if p.props.get("is_earner")]
        return earners[0] if earners else None

    def inferred_facts(self, pid: str) -> dict[str, dict]:
        """Rule-derived facts with provenance (e.g. Nominee typing, minor status)."""
        prov: Provenance = rule("rule:estate", 1.0)
        facts: dict[str, dict] = {}
        if self.nominated_assets(pid):
            facts["types"] = {"value": ["Person", "Nominee"], "provenance": prov.model_dump(mode="json")}
        if self.node(pid).props.get("dob"):
            facts["is_minor"] = {"value": self.is_minor(pid), "provenance": prov.model_dump(mode="json")}
        return facts
