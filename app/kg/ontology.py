"""Ontology loader, validator and RDF exporter."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator
from rdflib import BNode, Graph, Namespace, URIRef
from rdflib import Literal as RdfLiteral
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS, XSD

from app.core.masking import check_free_text, mask_identifier

ONTOLOGY_PATH = Path(__file__).with_name("ontology.yaml")

PropType = Literal["string", "text", "enum", "date", "bool", "number", "masked_id"]
_XSD = {"string": XSD.string, "text": XSD.string, "enum": XSD.string, "date": XSD.date,
        "bool": XSD.boolean, "number": XSD.decimal, "masked_id": XSD.string}


class OntologyError(ValueError):
    pass


class PropertyDef(BaseModel):
    type: PropType
    enum: str | None = None
    required: bool = False
    sensitive: bool = False
    default: Any = None
    description: str = ""


class ClassDef(BaseModel):
    description: str = ""
    subclass_of: str | None = None
    inferred: bool = False
    properties: dict[str, PropertyDef] = Field(default_factory=dict)


class RelationDef(BaseModel):
    domain: list[str]
    range: list[str]
    description: str = ""
    properties: dict[str, PropertyDef] = Field(default_factory=dict)


class Ontology(BaseModel):
    namespace: str
    prefix: str
    version: str
    enums: dict[str, list[str]]
    classes: dict[str, ClassDef]
    relations: dict[str, RelationDef]

    @model_validator(mode="after")
    def _check_refs(self) -> Ontology:
        def check_props(owner: str, props: dict[str, PropertyDef]) -> None:
            for name, p in props.items():
                if p.type == "enum" and p.enum not in self.enums:
                    raise OntologyError(f"{owner}.{name}: unknown enum {p.enum!r}")
                if p.type == "enum" and p.default is not None and p.default not in self.enums[p.enum]:
                    raise OntologyError(f"{owner}.{name}: default {p.default!r} not in enum")

        for cname, c in self.classes.items():
            if c.subclass_of and c.subclass_of not in self.classes:
                raise OntologyError(f"{cname}: unknown superclass {c.subclass_of!r}")
            check_props(cname, c.properties)
        for rname, r in self.relations.items():
            for cls in r.domain + r.range:
                if cls not in self.classes:
                    raise OntologyError(f"relation {rname}: unknown class {cls!r}")
            check_props(rname, r.properties)
        return self

    # ------------------------------------------------------------------ queries
    def all_properties(self, cls: str) -> dict[str, PropertyDef]:
        if cls not in self.classes:
            raise OntologyError(f"unknown class {cls!r}")
        c = self.classes[cls]
        inherited = self.all_properties(c.subclass_of) if c.subclass_of else {}
        return {**inherited, **c.properties}

    def sensitive_fields(self, cls: str) -> set[str]:
        return {n for n, p in self.all_properties(cls).items() if p.sensitive}

    def is_a(self, cls: str, ancestor: str) -> bool:
        while cls:
            if cls == ancestor:
                return True
            cls = self.classes[cls].subclass_of or ""
        return False

    # ------------------------------------------------------------------ validation
    def _coerce(self, owner: str, name: str, p: PropertyDef, value: Any) -> Any:
        if value is None:
            return None
        where = f"{owner}.{name}"
        match p.type:
            case "enum":
                if value not in self.enums[p.enum]:
                    raise OntologyError(f"{where}: {value!r} is not one of {self.enums[p.enum]}")
                return value
            case "date":
                if isinstance(value, date):
                    return value.isoformat()
                try:
                    return date.fromisoformat(str(value)).isoformat()
                except ValueError as e:
                    raise OntologyError(f"{where}: expected a date YYYY-MM-DD") from e
            case "bool":
                if not isinstance(value, bool):
                    raise OntologyError(f"{where}: expected true/false")
                return value
            case "number":
                if isinstance(value, bool) or not isinstance(value, int | float):
                    raise OntologyError(f"{where}: expected a number")
                return value
            case "masked_id":
                return mask_identifier(value, name)
            case _:  # string / text: both PII-guarded
                if not isinstance(value, str):
                    raise OntologyError(f"{where}: expected text")
                return check_free_text(value.strip(), name)

    def _validate(self, owner: str, props_def: dict[str, PropertyDef], props: dict, partial: bool) -> dict:
        unknown = set(props) - set(props_def)
        if unknown:
            raise OntologyError(f"{owner}: unknown properties {sorted(unknown)}")
        out: dict[str, Any] = {}
        for name, p in props_def.items():
            if name in props:
                out[name] = self._coerce(owner, name, p, props[name])
            elif not partial and p.default is not None:
                out[name] = p.default
            if not partial and p.required and out.get(name) in (None, ""):
                raise OntologyError(f"{owner}.{name} is required")
        return out

    def validate_node(self, cls: str, props: dict, partial: bool = False) -> dict:
        if cls not in self.classes or self.classes[cls].inferred:
            raise OntologyError(f"cannot assert nodes of class {cls!r}")
        return self._validate(cls, self.all_properties(cls), props, partial)

    def validate_edge(self, rel: str, src_cls: str, dst_cls: str, props: dict | None = None) -> dict:
        if rel not in self.relations:
            raise OntologyError(f"unknown relation {rel!r}")
        r = self.relations[rel]
        if not any(self.is_a(src_cls, d) for d in r.domain):
            raise OntologyError(f"{rel}: {src_cls} is not a valid source (expected {r.domain})")
        if not any(self.is_a(dst_cls, d) for d in r.range):
            raise OntologyError(f"{rel}: {dst_cls} is not a valid target (expected {r.range})")
        return self._validate(rel, r.properties, props or {}, partial=False)

    # ------------------------------------------------------------------ export
    def to_rdf(self) -> Graph:
        fv = Namespace(self.namespace)
        g = Graph()
        g.bind(self.prefix, fv)
        g.bind("owl", OWL)
        onto = URIRef(self.namespace.rstrip("#"))
        g.add((onto, RDF.type, OWL.Ontology))
        g.add((onto, OWL.versionInfo, RdfLiteral(self.version)))

        def union(classes: list[str]) -> URIRef | BNode:
            if len(classes) == 1:
                return fv[classes[0]]
            node, members = BNode(), BNode()
            Collection(g, members, [fv[c] for c in classes])
            g.add((node, RDF.type, OWL.Class))
            g.add((node, OWL.unionOf, members))
            return node

        for cname, c in self.classes.items():
            g.add((fv[cname], RDF.type, OWL.Class))
            g.add((fv[cname], RDFS.label, RdfLiteral(cname)))
            if c.description:
                g.add((fv[cname], RDFS.comment, RdfLiteral(c.description)))
            if c.subclass_of:
                g.add((fv[cname], RDFS.subClassOf, fv[c.subclass_of]))
            for pname, p in c.properties.items():
                prop = fv[f"{cname.lower()}_{pname}"]
                g.add((prop, RDF.type, OWL.DatatypeProperty))
                g.add((prop, RDFS.domain, fv[cname]))
                g.add((prop, RDFS.range, _XSD[p.type]))
                g.add((prop, fv.sensitive, RdfLiteral(p.sensitive)))
        for rname, r in self.relations.items():
            g.add((fv[rname], RDF.type, OWL.ObjectProperty))
            g.add((fv[rname], RDFS.domain, union(r.domain)))
            g.add((fv[rname], RDFS.range, union(r.range)))
            if r.description:
                g.add((fv[rname], RDFS.comment, RdfLiteral(r.description)))
        return g

    def to_turtle(self) -> str:
        return self.to_rdf().serialize(format="turtle")

    def to_jsonld(self) -> str:
        return self.to_rdf().serialize(format="json-ld", context={self.prefix: self.namespace})


def load_ontology(path: Path = ONTOLOGY_PATH) -> Ontology:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    try:
        return Ontology.model_validate(raw)
    except OntologyError:
        raise
    except ValueError as e:  # pydantic ValidationError wraps OntologyError raised in validators
        raise OntologyError(str(e)) from e


@lru_cache(maxsize=1)
def get_ontology() -> Ontology:
    return load_ontology()
