import pytest
import yaml

from app.config import ROOT
from app.core.checklist import DISCLAIMER, SCENARIOS, generate, next_of_kin
from tests.conftest import P

REF = yaml.safe_load((ROOT / "data/eval/reference_checklists.yaml").read_text())


@pytest.mark.parametrize("fid", ["family_a", "family_b", "family_c"])
@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_matches_reference(family_store, est_factory, fid, scenario):
    cl = generate(est_factory(family_store(fid)), scenario)
    ref = REF[fid][scenario]
    uni = [(s.action, set(s.actor_ids)) for s in cl.steps if not s.item_ids]
    assert uni == [(a, set(c)) for a, c in ref["universal"]]
    got = [(s.item_ids[0], s.action, set(s.actor_ids), s.blocked) for s in cl.steps if s.item_ids]
    assert got == [(i, a, set(c), b) for i, a, c, b in ref["steps"]]
    assert cl.disclaimer == DISCLAIMER
    assert [s.order for s in cl.steps] == list(range(1, len(cl.steps) + 1))


def test_steps_have_documents_and_institution(family_store, est_factory):
    cl = generate(est_factory(family_store("family_b")), "death_of_earner")
    for s in cl.steps:
        assert s.actors
        if s.item_ids:
            assert s.institution and s.required_documents
    lic = next(s for s in cl.steps if s.item_ids == ["b_lic"])
    assert lic.blocked_by == ["G07:b_lic/p_kamla"] and "cannot act" in lic.notes[0]
    assert "Bharat Life" in lic.text and '"Endowment policy"' in lic.text
    assert "No will" in cl.steps[1].notes[0]


def test_guardian_acts_for_minor_nominee(fresh, est_factory):
    s = fresh("family_a")
    s.add_edge("p_ananya", "guardian_of", "p_kabir", P)
    step = next(x for x in generate(est_factory(s), "death_of_earner").steps if x.item_ids == ["a_term"])
    assert not step.blocked
    assert step.actors == ["Ananya Mehta (guardian of Kabir Mehta)"]
    s.close()


def test_maturity_note_and_explicit_subject(family_store, est_factory):
    est = est_factory(family_store("family_c"))
    fd = next(x for x in generate(est, "death_of_earner").steps if x.item_ids == ["c_fd"])
    assert any("matures" in n for n in fd.notes)
    cl = generate(est, "incapacity", subject="p_gopal")
    assert [s.item_ids for s in cl.steps if s.item_ids] == [["c_parents_house"]]
    assert set(next_of_kin(est, "p_gopal")) == {"p_arjun", "p_lakshmi"}


def test_bad_inputs(family_store, est_factory):
    est = est_factory(family_store("family_a"))
    with pytest.raises(ValueError):
        generate(est, "zombie_apocalypse")
    with pytest.raises(KeyError):
        generate(est, "incapacity", subject="p_nobody")


def test_no_earner(empty_store, est_factory):
    with pytest.raises(ValueError, match="no subject"):
        generate(est_factory(empty_store), "incapacity")
