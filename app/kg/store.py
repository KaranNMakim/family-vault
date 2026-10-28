"""GraphStore interface and its NetworkX + SQLite implementation.

Each vault is one SQLite file. Sensitive properties (per the ontology) are written as
ciphertext; the decrypted graph only ever lives in memory (a NetworkX MultiDiGraph) while
the vault is unlocked.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import networkx as nx

from app.core.crypto import KdfParams, VaultCipher
from app.kg.ontology import Ontology, OntologyError, get_ontology
from app.kg.provenance import Provenance

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS nodes (id TEXT PRIMARY KEY, cls TEXT NOT NULL, props TEXT NOT NULL, prov TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS edges (id TEXT PRIMARY KEY, src TEXT NOT NULL, rel TEXT NOT NULL, dst TEXT NOT NULL,
                                  props TEXT NOT NULL, prov TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS records (kind TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL,
                                    PRIMARY KEY (kind, id));
CREATE TABLE IF NOT EXISTS audit (seq INTEGER PRIMARY KEY, body TEXT NOT NULL, prev_hash TEXT NOT NULL,
                                  hash TEXT NOT NULL);
"""


class NotFound(KeyError):
    pass


class LockedConnection:
    """sqlite3 connection safe to share across API worker threads (one statement at a time)."""

    def __init__(self, path: Path):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.RLock()

    def execute(self, sql: str, params: tuple = ()) -> list:
        with self._lock:
            return LockedCursor(self._conn.execute(sql, params).fetchall())

    def executescript(self, sql: str) -> None:
        with self._lock:
            self._conn.executescript(sql)

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class LockedCursor(list):
    """Rows already fetched under the lock; mimics the cursor methods we use."""

    def fetchall(self) -> list:
        return list(self)

    def fetchone(self):
        return self[0] if self else None


@dataclass
class Node:
    id: str
    cls: str
    props: dict[str, Any]
    prov: Provenance

    def to_dict(self) -> dict:
        return {"id": self.id, "cls": self.cls, "props": self.props, "provenance": self.prov.model_dump(mode="json")}


@dataclass
class Edge:
    id: str
    src: str
    rel: str
    dst: str
    props: dict[str, Any] = field(default_factory=dict)
    prov: Provenance | None = None

    def to_dict(self) -> dict:
        return {"id": self.id, "src": self.src, "rel": self.rel, "dst": self.dst, "props": self.props,
                "provenance": self.prov.model_dump(mode="json") if self.prov else None}


class GraphStore(Protocol):
    onto: Ontology

    def add_node(self, cls: str, props: dict, prov: Provenance, node_id: str | None = None) -> Node: ...
    def update_node(self, node_id: str, props: dict, prov: Provenance) -> Node: ...
    def delete_node(self, node_id: str) -> None: ...
    def get_node(self, node_id: str) -> Node: ...
    def nodes(self, cls: str | None = None) -> list[Node]: ...
    def add_edge(self, src: str, rel: str, dst: str, prov: Provenance, props: dict | None = None) -> Edge: ...
    def delete_edge(self, edge_id: str) -> None: ...
    def edges(self, rel: str | None = None, src: str | None = None, dst: str | None = None) -> list[Edge]: ...


def edge_id(src: str, rel: str, dst: str) -> str:
    return f"{src}|{rel}|{dst}"


class NetworkXSQLiteStore:
    """Write-through store: every mutation updates SQLite (encrypted) and the in-memory graph."""

    def __init__(self, path: Path, cipher: VaultCipher, onto: Ontology | None = None):
        self.path = Path(path)
        self.cipher = cipher
        self.onto = onto or get_ontology()
        self.db = LockedConnection(self.path)
        self.db.executescript(SCHEMA)
        self.g = nx.MultiDiGraph()
        self._load()

    # ------------------------------------------------------------------ lifecycle
    @classmethod
    def create(cls, path: Path, passphrase: str, meta: dict | None = None) -> NetworkXSQLiteStore:
        path = Path(path)
        if path.exists():
            raise FileExistsError(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        cipher, params, key_check = VaultCipher.create(passphrase)
        db = sqlite3.connect(path)
        db.executescript(SCHEMA)
        db.execute("INSERT INTO meta VALUES ('kdf', ?)", (json.dumps(params.to_dict()),))
        db.execute("INSERT INTO meta VALUES ('key_check', ?)", (key_check,))
        db.execute("INSERT INTO meta VALUES ('family', ?)", (json.dumps(meta or {}),))
        db.commit()
        db.close()
        return cls(path, cipher)

    @classmethod
    def open(cls, path: Path, passphrase: str) -> NetworkXSQLiteStore:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(path)
        db = sqlite3.connect(path)
        rows = dict(db.execute("SELECT key, value FROM meta").fetchall())
        db.close()
        cipher = VaultCipher.unlock(passphrase, KdfParams.from_dict(json.loads(rows["kdf"])), rows["key_check"])
        return cls(path, cipher)

    @staticmethod
    def read_public_meta(path: Path) -> dict:
        """Family display metadata (non-sensitive) without unlocking."""
        db = sqlite3.connect(path)
        try:
            row = db.execute("SELECT value FROM meta WHERE key='family'").fetchone()
            return json.loads(row[0]) if row else {}
        finally:
            db.close()

    def close(self) -> None:
        self.db.close()

    @property
    def meta(self) -> dict:
        row = self.db.execute("SELECT value FROM meta WHERE key='family'").fetchone()
        return json.loads(row[0]) if row else {}

    def set_totp_secret(self, secret: str) -> None:
        """Second-factor secret, stored encrypted with the vault key."""
        token = self.cipher.encrypt_bytes(secret.encode(), b"meta:totp")
        self.db.execute("INSERT OR REPLACE INTO meta VALUES ('totp', ?)", (token,))
        self.db.commit()

    def totp_secret(self) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key='totp'").fetchone()
        return self.cipher.decrypt_bytes(row[0], b"meta:totp").decode() if row else None

    def set_meta(self, meta: dict) -> None:
        self.db.execute("INSERT OR REPLACE INTO meta VALUES ('family', ?)", (json.dumps(meta),))
        self.db.commit()

    # ------------------------------------------------------------------ (de)serialisation
    def _encrypt_props(self, node_id: str, cls: str, props: dict) -> str:
        sensitive = self.onto.sensitive_fields(cls)
        out = {k: (self.cipher.encrypt_field(v, node_id, k) if k in sensitive and v is not None else v)
               for k, v in props.items()}
        return json.dumps(out)

    def _decrypt_props(self, node_id: str, cls: str, raw: str) -> dict:
        sensitive = self.onto.sensitive_fields(cls)
        props = json.loads(raw)
        return {k: (self.cipher.decrypt_field(v, node_id, k) if k in sensitive and v is not None else v)
                for k, v in props.items()}

    def _load(self) -> None:
        for nid, cls, props, prov in self.db.execute("SELECT id, cls, props, prov FROM nodes"):
            self.g.add_node(nid, cls=cls, props=self._decrypt_props(nid, cls, props),
                            prov=Provenance.model_validate_json(prov))
        for eid, src, rel, dst, props, prov in self.db.execute("SELECT id, src, rel, dst, props, prov FROM edges"):
            self.g.add_edge(src, dst, key=eid, rel=rel, props=json.loads(props),
                            prov=Provenance.model_validate_json(prov))

    # ------------------------------------------------------------------ nodes
    def add_node(self, cls: str, props: dict, prov: Provenance, node_id: str | None = None) -> Node:
        clean = self.onto.validate_node(cls, props)
        node_id = node_id or f"{cls[:3].lower()}_{uuid.uuid4().hex[:8]}"
        if node_id in self.g:
            raise OntologyError(f"node {node_id!r} already exists")
        self.db.execute("INSERT INTO nodes VALUES (?, ?, ?, ?)",
                        (node_id, cls, self._encrypt_props(node_id, cls, clean), prov.model_dump_json()))
        self.db.commit()
        self.g.add_node(node_id, cls=cls, props=clean, prov=prov)
        return self.get_node(node_id)

    def update_node(self, node_id: str, props: dict, prov: Provenance) -> Node:
        node = self.get_node(node_id)
        merged = {**node.props, **self.onto.validate_node(node.cls, props, partial=True)}
        merged = self.onto.validate_node(node.cls, merged)
        self.db.execute("UPDATE nodes SET props=?, prov=? WHERE id=?",
                        (self._encrypt_props(node_id, node.cls, merged), prov.model_dump_json(), node_id))
        self.db.commit()
        self.g.nodes[node_id].update(props=merged, prov=prov)
        return self.get_node(node_id)

    def delete_node(self, node_id: str) -> None:
        self.get_node(node_id)
        self.db.execute("DELETE FROM edges WHERE src=? OR dst=?", (node_id, node_id))
        self.db.execute("DELETE FROM nodes WHERE id=?", (node_id,))
        self.db.commit()
        self.g.remove_node(node_id)

    def get_node(self, node_id: str) -> Node:
        if node_id not in self.g:
            raise NotFound(node_id)
        d = self.g.nodes[node_id]
        return Node(node_id, d["cls"], dict(d["props"]), d["prov"])

    def nodes(self, cls: str | None = None) -> list[Node]:
        return [self.get_node(n) for n in sorted(self.g.nodes) if cls is None or self.g.nodes[n]["cls"] == cls]

    # ------------------------------------------------------------------ edges
    def add_edge(self, src: str, rel: str, dst: str, prov: Provenance, props: dict | None = None) -> Edge:
        s, d = self.get_node(src), self.get_node(dst)
        clean = self.onto.validate_edge(rel, s.cls, d.cls, props)
        eid = edge_id(src, rel, dst)
        if self.g.has_edge(src, dst, key=eid):
            raise OntologyError(f"edge {eid!r} already exists")
        self.db.execute("INSERT INTO edges VALUES (?, ?, ?, ?, ?, ?)",
                        (eid, src, rel, dst, json.dumps(clean), prov.model_dump_json()))
        self.db.commit()
        self.g.add_edge(src, dst, key=eid, rel=rel, props=clean, prov=prov)
        return Edge(eid, src, rel, dst, clean, prov)

    def delete_edge(self, eid: str) -> None:
        src, _, dst = eid.split("|", 2)
        if not self.g.has_edge(src, dst, key=eid):
            raise NotFound(eid)
        self.db.execute("DELETE FROM edges WHERE id=?", (eid,))
        self.db.commit()
        self.g.remove_edge(src, dst, key=eid)

    def edges(self, rel: str | None = None, src: str | None = None, dst: str | None = None) -> list[Edge]:
        out = []
        for s, d, k, data in self.g.edges(keys=True, data=True):
            if (rel and data["rel"] != rel) or (src and s != src) or (dst and d != dst):
                continue
            out.append(Edge(k, s, data["rel"], d, dict(data["props"]), data["prov"]))
        return sorted(out, key=lambda e: e.id)

    # ------------------------------------------------------------------ side records (access requests etc.)
    def put_record(self, kind: str, rid: str, body: dict) -> None:
        self.db.execute("INSERT OR REPLACE INTO records VALUES (?, ?, ?)", (kind, rid, json.dumps(body)))
        self.db.commit()

    def get_records(self, kind: str) -> list[dict]:
        rows = self.db.execute("SELECT body FROM records WHERE kind=? ORDER BY id", (kind,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    # ------------------------------------------------------------------ dump / load (export-import)
    def dump(self) -> dict:
        return {
            "meta": self.meta,
            "nodes": [n.to_dict() for n in self.nodes()],
            "edges": [e.to_dict() for e in self.edges()],
            "records": {k: self.get_records(k) for (k,) in self.db.execute("SELECT DISTINCT kind FROM records")},
        }

    def load_dump(self, data: dict) -> None:
        """Load a dump into an EMPTY store, re-validating everything against the ontology."""
        if self.g.number_of_nodes():
            raise OntologyError("target vault is not empty")
        self.set_meta(data.get("meta", {}))
        for n in data["nodes"]:
            self.add_node(n["cls"], n["props"], Provenance.model_validate(n["provenance"]), node_id=n["id"])
        for e in data["edges"]:
            self.add_edge(e["src"], e["rel"], e["dst"], Provenance.model_validate(e["provenance"]), e["props"])
        for kind, rows in data.get("records", {}).items():
            for body in rows:
                self.put_record(kind, body["id"], body)
