# Changelog

## Phase 0 — scaffold
- uv/Python 3.12 project, ruff, pytest(+cov), FastAPI `/health`, redacting JSON logger.
- `scripts/tasks.py` task runner; `Makefile` and `make.cmd` shim delegate to it.

## Phase 1 — ontology + crypto
- `app/kg/ontology.yaml` (7 classes, 7 relations, enums) with validating loader; Turtle/JSON-LD export via rdflib; `GET /ontology?format=json|turtle|jsonld`.
- `app/core/crypto.py`: Argon2id KDF, XChaCha20-Poly1305 field encryption bound to record+field (AAD), key-check token, encrypted export blobs.
- `app/core/masking.py`: last-4-only identifiers; rejects full account/card numbers, Aadhaar/PAN-like values, passwords/PIN/OTP, forbidden keys.
- `app/kg/llm.py`: LLMClient (mock default / Anthropic live) with a structural-only context guard; `app/kg/provenance.py`.

## Phase 2 — graph + gap rules
- `GraphStore` protocol + `NetworkXSQLiteStore` (write-through SQLite, sensitive props encrypted, provenance on every node/edge, dump/load).
- `app/core/estate.py` query helpers + rule-derived facts (Nominee typing, minor status) with `method: rule` provenance.
- 8 deterministic gap rules G01–G08 (`app/core/gaps.py`) with severity, plain-language fix and one-click `fix_action`.
- Readiness score 0–100 with capped category breakdown and per-gap "points if fixed".
- Three synthetic families (`data/seed/`) + planted-gap manifest (`data/eval/gap_manifest.yaml`, 23 gaps + 5 negative controls); `python -m app.seed`.

## Phase 3 — checklist + emergency access
- `app/core/checklist.py`: scenarios death_of_earner / incapacity / loss_of_documents → ordered steps per institution with documents, actors (nominee → guardian of minor → joint holder → next of kin) and gap-driven blocking; general-guidance disclaimer; LLM rephrasing via structural templates only.
- 9 hand-written reference checklists (`data/eval/reference_checklists.yaml`).
- `app/core/emergency.py`: request → waiting period → owner notified/cancel → activate after delay → 7-day read-only scope → expiry; simulated clock.
- `app/core/access.py`: Owner / Spouse (full|shared) / Nominee / Advisor / Emergency scoped views and field redaction.
- `app/core/audit.py`: hash-chained, redacted audit log with tamper verification.

## Phase 4 — API
- Full FastAPI surface: `/families`, `/session/{unlock,act-as,personas}`, `/vaults`, CRUD for `/people /assets /liabilities /documents /institutions /advisors`, `/relations`, `/graph`, `/gaps`, `/readiness`, `/checklist/{scenario}` (+ `/pdf`), `/access-requests` (create, cancel, approve-after-delay, view), `/notifications`, `/demo/clock`, `/audit`, `/export`, `/import`, `/onboarding`.
- Global body guard rejects forbidden keys (password, PIN, Aadhaar, account_number, …); masking errors return 422 with a plain-language "why".
- Every read/change of the vault is audited; role scoping applied to every response.
- Conversational onboarding engine (`app/core/onboarding.py`) with skippable sections and progress.
- LLM guard now permits single/double digits (e.g. "last 4 digits") but rejects runs of 3+.

## Phase 5 — web app
- Next.js 15 (App Router) + TypeScript + Tailwind v4 + Cytoscape.js in `web/`.
- Pages: start/unlock, overview (readiness ring + "fix these first"), onboarding (guided conversation + form fallback, progress, skippable), estate map (gap rings, legend, details panel with provenance), gaps (one-click fixes), checklist (3 scenarios, print + PDF), nominee view, emergency-access simulation (timeline, cancel, demo clock), vault & audit (encrypted export/import, hash-chain status).
- Role switcher (owner / spouse / nominee / advisor / emergency), always-visible demo banner, 18px base type, mobile nav.
- Client-side mirror of the masking guard; vitest smoke + unit tests (22).
- Minors can no longer file emergency-access requests (guardian should). CORS allows any localhost port for the local demo.

## Phase 6 — eval, docs, polish
- `make eval` (`app/eval.py`) → `docs/eval-report.md`: gap P/R 100%/100% (23 planted, 5 negative controls clean), 9/9 checklists exact vs references, crypto 7/7, masking 22/22 full-number inputs rejected (8/8 valid accepted), 0 family values in LLM payloads.
- `docs/security.md` (threat model, key loss), `docs/demo-script.md` (3 flows), full README (mermaid architecture, mocked vs real, productization).
- Fixes found during browser testing: SQLite connection now thread-safe across API workers; onboarding chat no longer crashes in browsers where `scrollIntoView` returns a Promise; expired sessions return the user to the start page; "an insurance policy" wording; owner session gets its person id once the owner is created in onboarding.
