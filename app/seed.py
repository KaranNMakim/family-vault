"""Build encrypted demo vaults from the synthetic family YAML files.  `python -m app.seed`"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from app.config import get_settings
from app.kg.provenance import human
from app.kg.store import NetworkXSQLiteStore


def load_family(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def family_files(seed_dir: Path | None = None) -> list[Path]:
    return sorted((seed_dir or get_settings().seed_dir).glob("family_*.yaml"))


def populate(store: NetworkXSQLiteStore, fam: dict) -> None:
    prov = human(f"seed:{fam['id']}")
    for pid, props in fam["people"].items():
        store.add_node("Person", props, prov, node_id=pid)
    for iid, props in fam["institutions"].items():
        store.add_node("Institution", props, prov, node_id=iid)
    for aid, props in (fam.get("advisors") or {}).items():
        store.add_node("Advisor", props, prov, node_id=aid)
    for section, cls in (("assets", "Asset"), ("liabilities", "Liability")):
        for item_id, spec in (fam.get(section) or {}).items():
            store.add_node(cls, spec["props"], prov, node_id=item_id)
            for owner in spec.get("owners", []):
                oid, role = (owner, "owner") if isinstance(owner, str) else (owner["id"], owner["role"])
                store.add_edge(oid, "owns", item_id, prov, {"role": role})
            for nid in spec.get("nominees", []):
                store.add_edge(nid, "nominee_of", item_id, prov)
            if spec.get("held_at"):
                store.add_edge(item_id, "held_at", spec["held_at"], prov)
            for adv in spec.get("advised_by", []):
                store.add_edge(item_id, "advised_by", adv, prov)
            for pid in spec.get("knows", []):
                store.add_edge(pid, "knows_about", item_id, prov)
            for i, doc in enumerate(spec.get("docs", []), start=1):
                did = f"d_{item_id}_{i}"
                store.add_node("Document", doc, prov, node_id=did)
                store.add_edge(item_id, "documented_by", did, prov)
    for guardian, minor in fam.get("guardians") or []:
        store.add_edge(guardian, "guardian_of", minor, prov)


def public_meta(fam: dict) -> dict:
    return {k: fam[k] for k in ("id", "display_name", "story", "owner", "primary_earner")} | {"synthetic": True}


def build_vault(fam: dict, vault_dir: Path, force: bool = True) -> Path:
    path = vault_dir / f"{fam['id']}.db"
    if path.exists():
        if not force:
            return path
        path.unlink()
    store = NetworkXSQLiteStore.create(path, fam["demo_passphrase"], public_meta(fam))
    try:
        populate(store, fam)
    finally:
        store.close()
    return path


def seed_all(vault_dir: Path | None = None, force: bool = True) -> list[Path]:
    vault_dir = vault_dir or get_settings().vault_dir
    return [build_vault(load_family(f), vault_dir, force) for f in family_files()]


if __name__ == "__main__":
    for p in seed_all(force="--keep" not in sys.argv):
        print(f"seeded {p}")
