import pytest
from pydantic import ValidationError

from app.kg.llm import MockLLM, StructuralContext, fill, get_llm
from app.kg.provenance import human, rule


def ctx(**fields):
    return StructuralContext(task="checklist_step", fields=fields)


def test_mock_is_deterministic_and_records_calls():
    llm = MockLLM()
    c = ctx(template="Call {institution} and report the death.", asset_type="insurance", step_index=2)
    assert llm.rephrase(c) == llm.rephrase(c) == "Call {institution} and report the death."
    assert len(llm.calls) == 2


@pytest.mark.parametrize(
    "fields",
    [
        {"name": "Rohan"},  # non-whitelisted key
        {"template": "Account 50100234567890"},  # digits
        {"template": "Policy XXXX1234"},  # digits even when masked
        {"people_count": 123456},  # large number
        {"doc_types": ["policy_document", "ABCDE1234F"]},
    ],
)
def test_guard_blocks_data(fields):
    with pytest.raises(ValidationError):
        ctx(**fields)


def test_guard_allows_structure():
    c = ctx(template="Ask {actor} to visit {institution}.", blocked=True, doc_types=["will", "title_deed"])
    assert c.template.startswith("Ask")


def test_default_client_is_mock():
    assert get_llm().mode == "mock"


def test_fill_after_llm():
    assert fill("Visit {institution}", institution="Bharat Bank") == "Visit Bharat Bank"


def test_provenance_helpers():
    assert human("api").method == "human"
    p = rule("gap-engine", 0.9)
    assert p.method == "rule" and p.confidence == 0.9
