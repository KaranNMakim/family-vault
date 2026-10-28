# Changelog

## Phase 0 — scaffold
- uv/Python 3.12 project, ruff, pytest(+cov), FastAPI `/health`, redacting JSON logger.
- `scripts/tasks.py` task runner; `Makefile` and `make.cmd` shim delegate to it.

## Phase 1 — ontology + crypto
- `app/kg/ontology.yaml` (7 classes, 7 relations, enums) with validating loader; Turtle/JSON-LD export via rdflib; `GET /ontology?format=json|turtle|jsonld`.
- `app/core/crypto.py`: Argon2id KDF, XChaCha20-Poly1305 field encryption bound to record+field (AAD), key-check token, encrypted export blobs.
- `app/core/masking.py`: last-4-only identifiers; rejects full account/card numbers, Aadhaar/PAN-like values, passwords/PIN/OTP, forbidden keys.
- `app/kg/llm.py`: LLMClient (mock default / Anthropic live) with a structural-only context guard; `app/kg/provenance.py`.
