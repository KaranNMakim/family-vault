import copy
import json

import pytest
import yaml
from rdflib import Graph

from app.core.masking import MaskingError
from app.kg.ontology import ONTOLOGY_PATH, OntologyError, get_ontology, load_ontology


@pytest.fixture(scope="module")
def onto():
    return get_ontology()


def test_loads_all_classes_and_relations(onto):
    assert {"Person", "Nominee", "Asset", "Liability", "Document", "Institution", "Advisor"} <= set(onto.classes)
    assert {"owns", "nominee_of", "held_at", "documented_by", "guardian_of", "advised_by",
            "knows_about"} == set(onto.relations)
    assert set(onto.enums["asset_type"]) == {"insurance", "fixed_deposit", "bank_account", "demat",
                                              "mutual_fund", "property", "vehicle", "other"}


def test_nominee_inherits_person(onto):
    assert onto.is_a("Nominee", "Person")
    assert "dob" in onto.all_properties("Nominee")
    assert onto.sensitive_fields("Person") == {"dob"}
    assert {"masked_id", "notes"} == onto.sensitive_fields("Asset")


def test_validate_node_defaults_and_coercion(onto):
    out = onto.validate_node("Asset", {"asset_type": "insurance", "label": "Term plan", "masked_id": "1234",
                                       "maturity_date": "2027-01-05"})
    assert out["masked_id"] == "XXXX1234"
    assert out["value_band"] == "unknown"


@pytest.mark.parametrize(
    "props,err",
    [
        ({"label": "x"}, "required"),
        ({"asset_type": "gold", "label": "x"}, "not one of"),
        ({"asset_type": "other", "label": "x", "maturity_date": "tomorrow"}, "date"),
        ({"asset_type": "other", "label": "x", "colour": "red"}, "unknown properties"),
        ({"asset_type": "other", "label": 5}, "text"),
    ],
)
def test_validate_node_errors(onto, props, err):
    with pytest.raises(OntologyError, match=err):
        onto.validate_node("Asset", props)


def test_validate_node_type_errors(onto):
    with pytest.raises(OntologyError, match="true/false"):
        onto.validate_node("Person", {"name": "A", "is_alive": "yes"})
    with pytest.raises(OntologyError, match="cannot assert"):
        onto.validate_node("Nominee", {"name": "A"})
    with pytest.raises(OntologyError, match="number"):
        onto.validate_edge("nominee_of", "Person", "Asset", {"share_pct": "fifty"})


def test_validate_node_rejects_full_numbers(onto):
    with pytest.raises(MaskingError):
        onto.validate_node("Asset", {"asset_type": "bank_account", "label": "Savings", "masked_id": "50100234567890"})
    with pytest.raises(MaskingError):
        onto.validate_node("Document", {"doc_type": "will", "label": "Will", "location": "PAN ABCDE1234F"})


def test_partial_validation(onto):
    assert onto.validate_node("Asset", {"label": "Renamed"}, partial=True) == {"label": "Renamed"}


def test_validate_edge_domain_range(onto):
    assert onto.validate_edge("owns", "Person", "Liability", {"role": "co_borrower"}) == {"role": "co_borrower"}
    with pytest.raises(OntologyError, match="source"):
        onto.validate_edge("owns", "Asset", "Asset")
    with pytest.raises(OntologyError, match="target"):
        onto.validate_edge("nominee_of", "Person", "Liability")
    with pytest.raises(OntologyError, match="unknown relation"):
        onto.validate_edge("loves", "Person", "Person")


def test_rdf_exports_parse(onto):
    g = Graph().parse(data=onto.to_turtle(), format="turtle")
    assert len(g) > 50
    doc = json.loads(onto.to_jsonld())
    assert doc
    g2 = Graph().parse(data=onto.to_jsonld(), format="json-ld")
    assert len(g2) == len(g)


def _write(tmp_path, raw):
    p = tmp_path / "o.yaml"
    p.write_text(yaml.safe_dump(raw))
    return p


@pytest.mark.parametrize(
    "mutate,err",
    [
        (lambda r: r["classes"]["Nominee"].update(subclass_of="Ghost"), "superclass"),
        (lambda r: r["relations"]["owns"].update(range=["Ghost"]), "unknown class"),
        (lambda r: r["classes"]["Asset"]["properties"]["asset_type"].update(enum="nope"), "unknown enum"),
        (lambda r: r["classes"]["Asset"]["properties"]["value_band"].update(default="huge"), "default"),
    ],
)
def test_invalid_ontology_rejected(tmp_path, mutate, err):
    raw = yaml.safe_load(ONTOLOGY_PATH.read_text())
    bad = copy.deepcopy(raw)
    mutate(bad)
    with pytest.raises(OntologyError, match=err):
        load_ontology(_write(tmp_path, bad))
