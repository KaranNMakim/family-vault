import pytest
import yaml

from app.config import ROOT
from app.core.gaps import RULES, detect_gaps
from app.core.readiness import CATEGORIES, band, readiness
from tests.conftest import P

MANIFEST = yaml.safe_load((ROOT / "data/eval/gap_manifest.yaml").read_text())


@pytest.mark.parametrize("fid", ["family_a", "family_b", "family_c"])
def test_seeded_families_match_manifest(family_store, est_factory, fid):
    got = {g.key for g in detect_gaps(est_factory(family_store(fid)))}
    assert got == {x["key"] for x in MANIFEST["families"][fid]}
    assert not got & set(MANIFEST["negative_controls"])


def test_all_eight_rules_registered():
    assert sorted(RULES) == [f"G0{i}" for i in range(1, 9)]


def test_every_gap_has_fix_and_action(family_store, est_factory):
    for fid in ("family_a", "family_b", "family_c"):
        for g in detect_gaps(est_factory(family_store(fid))):
            assert g.fix and g.message and g.fix_action.get("kind")
            assert g.severity in {"critical", "high", "medium", "low", "info"}


def test_fixing_gaps_removes_them(fresh, est_factory):
    s = fresh("family_a")
    est = est_factory(s)
    keys = {g.key for g in detect_gaps(est)}
    s.add_edge("p_ananya", "guardian_of", "p_kabir", P)        # G03
    s.add_edge("p_rohan", "nominee_of", "a_fd_ananya", P)       # G01
    d = s.add_node("Document", {"doc_type": "cas_statement", "label": "CAS"}, P)
    s.add_edge("a_mf", "documented_by", d.id, P)                # G05
    s.add_edge("p_ananya", "knows_about", "a_demat", P)         # G06
    after = {g.key for g in detect_gaps(est)}
    assert keys - after == {"G03:p_kabir", "G01:a_fd_ananya", "G05:a_mf", "G06:a_demat"}
    s.close()


def test_maturity_window_edges(empty_store, est_factory):
    s = empty_store
    s.add_node("Person", {"name": "A"}, P, node_id="p")
    for i, (d, t) in enumerate([("2026-11-10", "fixed_deposit"), ("2026-12-20", "insurance"),
                                ("2026-09-15", "fixed_deposit"), ("2027-06-01", "fixed_deposit"),
                                ("2026-11-05", "bank_account")]):
        field = "expiry_date" if t == "insurance" else "maturity_date"
        s.add_node("Asset", {"asset_type": t, "label": f"X{'abcde'[i]}", field: d}, P, node_id=f"a{i}")
    gaps = {g.key: g for g in detect_gaps(est_factory(s)) if g.rule == "G04"}
    assert set(gaps) == {"G04:a0", "G04:a1", "G04:a2"}
    assert gaps["G04:a0"].severity == "high" and gaps["G04:a1"].severity == "medium"
    assert "unclaimed" in gaps["G04:a2"].title.lower()


def test_deceased_vs_unreachable_severity(empty_store, est_factory):
    s = empty_store
    s.add_node("Person", {"name": "Owner"}, P, node_id="o")
    s.add_node("Person", {"name": "Gone", "is_alive": False}, P, node_id="g")
    s.add_node("Person", {"name": "Lost", "reachable": False}, P, node_id="l")
    s.add_node("Asset", {"asset_type": "insurance", "label": "Pol"}, P, node_id="a")
    s.add_edge("o", "owns", "a", P)
    s.add_edge("g", "nominee_of", "a", P)
    s.add_edge("l", "nominee_of", "a", P)
    g7 = {g.key: g.severity for g in detect_gaps(est_factory(s)) if g.rule == "G07"}
    assert g7 == {"G07:a/g": "critical", "G07:a/l": "high"}


def test_bank_account_needs_any_one_document(empty_store, est_factory):
    s = empty_store
    s.add_node("Asset", {"asset_type": "bank_account", "label": "S"}, P, node_id="a")
    assert any(g.key == "G05:a" for g in detect_gaps(est_factory(s)))
    s.add_node("Document", {"doc_type": "bank_statement", "label": "St"}, P, node_id="d")
    s.add_edge("a", "documented_by", "d", P)
    assert not any(g.key == "G05:a" for g in detect_gaps(est_factory(s)))


def test_readiness_breakdown_and_impacts(family_store, est_factory):
    gaps = detect_gaps(est_factory(family_store("family_c")))
    r = readiness(gaps)
    assert r.score == sum(c.earned for c in r.categories)
    assert sum(mx for _, mx in CATEGORIES.values()) == 100
    assert 0 <= r.score <= 100
    assert {i.key for i in r.impacts} == {g.key for g in gaps}
    best = r.impacts[0]
    assert best.points_if_fixed >= r.impacts[-1].points_if_fixed
    assert readiness([]).score == 100


def test_readiness_category_cap(family_store, est_factory):
    gaps = detect_gaps(est_factory(family_store("family_c")))
    docs = next(c for c in readiness(gaps).categories if c.category == "documents")
    assert docs.lost == min(docs.max_points, 4 * 4 + 8)  # 4 medium + 1 high (property)


@pytest.mark.parametrize("score,label", [(90, "Well prepared"), (70, "Mostly prepared"), (50, "Some important gaps"),
                                         (10, "At risk")])
def test_bands(score, label):
    assert band(score) == label


def test_inferred_facts(family_store, est_factory):
    est = est_factory(family_store("family_a"))
    facts = est.inferred_facts("p_kabir")
    assert facts["types"]["value"] == ["Person", "Nominee"]
    assert facts["is_minor"]["value"] is True
    assert facts["is_minor"]["provenance"]["method"] == "rule"
    assert est.earner() == "p_rohan"
    assert est.inferred_facts("p_myra") == {"is_minor": est.inferred_facts("p_myra")["is_minor"]}
