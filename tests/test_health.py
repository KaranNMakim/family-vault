import json
import logging

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.logs import JsonFormatter, redact


def test_health():
    client = TestClient(create_app())
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["demo"] is True


def test_redact_sensitive_keys_and_digit_runs():
    out = redact({"passphrase": "hunter2", "nested": {"masked_id": "1234"}, "msg": "acct 123456789"})
    assert out["passphrase"] == "[REDACTED]"
    assert out["nested"]["masked_id"] == "[REDACTED]"
    assert "123456789" not in out["msg"]


def test_json_formatter_redacts_extra():
    rec = logging.LogRecord("vault.t", logging.INFO, "", 0, "hello %s", ("x",), None)
    rec.notes = "secret note"
    line = json.loads(JsonFormatter().format(rec))
    assert line["msg"] == "hello x"
    assert line["notes"] == "[REDACTED]"


def test_ontology_endpoint_formats():
    client = TestClient(create_app())
    assert "Person" in client.get("/ontology").json()["classes"]
    assert "owl:Class" in client.get("/ontology?format=turtle").text
    assert client.get("/ontology?format=jsonld").headers["content-type"].startswith("application/ld+json")
