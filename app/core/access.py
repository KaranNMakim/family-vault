"""Role-based, scoped views of the estate graph.

Roles: owner (everything), spouse (full, or 'shared' = what they own/co-own/are nominee of/know about),
nominee (read-only; assets where they are nominee), advisor (assets advised_by them; sensitive fields hidden),
emergency (read-only nominee-like scope granted by an activated emergency-access request).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.core.estate import Estate
from app.core.gaps import Gap
from app.kg.store import Node

Role = Literal["owner", "spouse", "nominee", "advisor", "emergency"]
WRITE_ROLES = {"owner", "spouse"}


class Principal(BaseModel):
    role: Role
    person_id: str | None = None  # Person node (owner/spouse/nominee/emergency)
    advisor_id: str | None = None
    spouse_scope: Literal["full", "shared"] = "full"
    access_request_id: str | None = None

    @property
    def can_write(self) -> bool:
        return self.role == "owner" or (self.role == "spouse" and self.spouse_scope == "full")

    @property
    def actor(self) -> str:
        return self.person_id or self.advisor_id or "anonymous"


class AccessDenied(PermissionError):
    pass


def visible_items(est: Estate, pr: Principal) -> set[str]:
    all_items = {n.id for n in est.assets() + est.liabilities()}
    if pr.role == "owner" or (pr.role == "spouse" and pr.spouse_scope == "full"):
        return all_items
    if pr.role == "spouse":
        pid = pr.person_id
        known = {e.dst for e in est.store.edges(rel="knows_about", src=pid)}
        return (set(est.owned_by(pid)) | set(est.nominated_assets(pid)) | known) & all_items
    if pr.role in ("nominee", "emergency"):
        return set(est.nominated_assets(pr.person_id or ""))
    if pr.role == "advisor":
        return set(est.advised_items(pr.advisor_id or ""))
    return set()


def _hidden_fields(est: Estate, pr: Principal, node: Node) -> set[str]:
    if pr.role == "owner" or (pr.role == "spouse" and pr.spouse_scope == "full"):
        return set()
    sensitive = est.store.onto.sensitive_fields(node.cls)
    if pr.role == "advisor":
        return sensitive
    # spouse(shared) / nominee / emergency keep masked ids and document locations (needed to claim),
    # but never private notes or other people's dates of birth.
    hidden = {"notes"} & sensitive
    if node.cls == "Person" and node.id != pr.person_id:
        hidden |= {"dob"}
    return hidden


def redact_node(est: Estate, pr: Principal, node: Node) -> dict:
    d = node.to_dict()
    hidden = _hidden_fields(est, pr, node)
    d["props"] = {k: v for k, v in d["props"].items() if k not in hidden}
    if hidden:
        d["hidden_fields"] = sorted(hidden)
    return d


def scoped_graph(est: Estate, pr: Principal) -> dict:
    """Nodes and edges this principal may see: visible items plus their people, institutions and documents."""
    items = visible_items(est, pr)
    full = pr.role == "owner" or (pr.role == "spouse" and pr.spouse_scope == "full")
    node_ids = set(items)
    edges = []
    for e in est.store.edges():
        touches_item = e.src in items or e.dst in items
        if full or touches_item:
            if not full and e.rel == "knows_about" and pr.role in ("nominee", "emergency", "advisor"):
                continue
            edges.append(e)
            node_ids |= {e.src, e.dst}
    if full:
        node_ids |= {n for n in est.store.g.nodes}
    if pr.person_id:
        node_ids.add(pr.person_id)
    if pr.advisor_id:
        node_ids.add(pr.advisor_id)
    nodes = [redact_node(est, pr, est.node(n)) for n in sorted(node_ids)]
    if not full:
        # Guardianship edges matter to nominees (minor nominees) - include those between visible people.
        edges += [e for e in est.store.edges(rel="guardian_of") if e.src in node_ids and e.dst in node_ids
                  and e not in edges]
    return {"nodes": nodes, "edges": [e.to_dict() for e in edges], "visible_items": sorted(items)}


def scoped_gaps(gaps: list[Gap], est: Estate, pr: Principal) -> list[Gap]:
    if pr.role == "owner" or (pr.role == "spouse" and pr.spouse_scope == "full"):
        return gaps
    items = visible_items(est, pr)
    return [g for g in gaps if set(g.subject_ids) & items]


def require_item(est: Estate, pr: Principal, item_id: str) -> None:
    if item_id not in visible_items(est, pr):
        raise AccessDenied(f"{pr.role} cannot access {item_id}")


def require_write(pr: Principal) -> None:
    if not pr.can_write:
        raise AccessDenied(f"{pr.role} has read-only access")
