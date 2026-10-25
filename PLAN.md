# family-vault — POV plan

A household estate graph for Indian families: record *where* assets, nominees and
documents are, find gaps, and generate an "if something happens" checklist.
Proof-of-value, synthetic data only. Target: a family member "gets it" in 5 minutes.

## 1. Architecture

```
            ┌──────────────────────── web (Next.js App Router, TS, Tailwind, Cytoscape) ───────────────────────┐
            │ Unlock/family picker · Onboarding (chat + form) · Estate map · Gaps · Readiness · Checklist     │
            │ Nominee view · Emergency access timeline · Role switcher · DEMO banner                         │
            └──────────────────────────────────────────────┬───────────────────────────────────────────────────┘
                                                           │ JSON over HTTP (bearer session token)
┌──────────────────────────────────────────── app/api (FastAPI) ─────────────────────────────────────────────────┐
│ /health /ontology /session/* /people /assets /liabilities /documents /institutions /gaps /readiness            │
│ /checklist/{scenario}(.pdf) /access-requests /audit /export /import /onboarding/* /demo/clock                  │
│ middleware: input masking guard · role-scoped views · audit · redacting JSON logs                              │
└──────────────────────────────┬──────────────────────────────────────────────────────┬──────────────────────────┘
                               │                                                      │
┌──────────── app/core (pure, deterministic) ───────────┐            ┌──────────── app/kg ─────────────────────────┐
│ masking   – reject full numbers / IDs / secrets       │            │ ontology.yaml + loader/validator            │
│ crypto    – Argon2id KDF + XSalsa20-Poly1305 fields   │            │   → JSON-LD / Turtle export (rdflib)        │
│ gaps      – 8 rule engine, severity + fix + action    │            │ GraphStore interface                        │
│ readiness – 0-100 weighted categories, what-if deltas │            │   NetworkXSQLiteStore (MultiDiGraph+SQLite) │
│ checklist – scenario templates × graph → steps        │            │ Provenance on every node/edge               │
│ access    – Owner/Spouse/Nominee/Advisor scoping      │            │ LLMClient (mock | Anthropic live)           │
│ emergency – request → wait → cancel/activate          │            └─────────────────────────────────────────────┘
│ audit     – hash-chained log · export/import          │
│ onboarding– slot state machine (LLM only rephrases)   │
└───────────────────────────────────────────────────────┘
                     SQLite per vault: data/vaults/<family>.db (sensitive fields ciphertext only)
```

Data flow: unlock (passphrase → Argon2id → key held in server memory for the session) →
store decrypts sensitive fields into an in-memory NetworkX graph → rule engines read the graph →
API applies the caller's role scope before serialising → audit entry written.

## 2. Build order (phases)

| # | Phase | Output | Exit test |
|---|-------|--------|-----------|
| 0 | Scaffold + tooling | pyproject (uv, py3.12), ruff, pytest, Makefile + `make.cmd` shim, `/health`, git | `make test` green |
| 1 | Ontology + crypto | ontology.yaml, loader/validator, RDF export, `/ontology`; crypto + masking modules | crypto + masking + ontology tests |
| 2 | Graph + gap rules | GraphStore, provenance, seed loader, 3 synthetic families + gap manifest, 8 rules, readiness | rule unit tests, manifest P/R = 1.0 |
| 3 | Checklist + emergency access | scenario engine, reference checklists, access-request state machine, audit chain | checklist + emergency tests |
| 4 | API | all endpoints, role scoping, export/import, onboarding engine, PDF | contract tests |
| 5 | Web | all pages, mobile-first, large type | build + smoke test |
| 6 | Eval + docs | `make eval` → docs/eval-report.md, security.md, demo-script.md, README | DoD checklist |

After each phase: tests → README/CHANGELOG → commit → 5-line summary.

## 3. Key design decisions

- **Masked identifiers only.** `core/masking.py` accepts `1234`, `XXXX1234`, `****1234`
  (≤4 visible chars). It rejects ≥5 consecutive digits anywhere in an identifier field, and
  in every free-text field rejects runs of ≥6 digits, Aadhaar-like (12 digits, spaced or not),
  PAN-like (`ABCDE1234F`), card-like numbers, and words like password/PIN/OTP/CVV followed by a value.
  The error says *why* ("we only need the last 4 digits to help your family find the account").
- **Field-level encryption.** Fields marked `sensitive: true` in the ontology are stored as
  `nacl.secret.SecretBox` ciphertext (XSalsa20-Poly1305, random 24-byte nonce, MAC = tamper
  detection). Key = Argon2id(passphrase, 16-byte salt, MODERATE ops/mem). Only the salt and a
  key-check ciphertext are stored. Wrong passphrase → MAC failure → 401.
- **Provenance** `{source, timestamp, confidence, method: rule|model|human}` on every node and edge.
  Derived facts (e.g. inferred `Nominee` type, minor status) are tagged `method: rule`.
- **Deterministic engines.** Gaps, readiness and checklists never call the LLM. The LLM only
  (a) rephrases onboarding questions and (b) rewrites checklist step wording. Both receive a
  `StructuralContext` (whitelisted keys, enum values, counts) — never names, ids, dates, notes.
  `LLMClient` runs a guard that refuses any payload containing digits ≥3 long or non-whitelisted keys.
- **Clock.** Rules that depend on "today" take `as_of`. Demo/eval default `as_of = 2026-11-01`
  (env `VAULT_AS_OF`), so seeds and eval numbers are reproducible. Emergency access uses a
  simulated clock that the demo can fast-forward.
- **Roles.** A principal = (role, person_id, scope). Owner: everything. Spouse: full or
  `shared` (assets they own, co-own, are nominee of, or know about). Nominee: read-only,
  assets where they are nominee + the institution and document *locations* needed to claim.
  Advisor: assets `advised_by` them, sensitive fields hidden. Emergency grantee: Nominee-like
  scope, time-boxed.
- **Audit** is append-only and hash-chained (each entry stores `sha256(prev_hash + entry)`),
  so tampering is detectable. Details are redacted before writing.

## 4. Assumptions

1. Windows dev box; `make` is not installed, so a `make.cmd` shim runs the same targets via
   `scripts/tasks.py` (PowerShell: `.\make demo`; cmd/Git-Bash-with-make: `make demo`).
2. "Offline" means after the one-time `uv sync` / `npm install`; no network at runtime (LLM_MODE=mock).
3. `Nominee` is modelled as a subclass of `Person` (a person who is `nominee_of` ≥1 asset), inferred by rule.
4. Co-borrowers are `owns` edges on a Liability with `role: co_borrower`; loan cover is a
   `documented_by` Document of type `loan_cover_note`. G08 applies to loans, not credit cards.
5. G01 (no nominee) applies to asset types where Indian nomination exists in practice:
   insurance, fixed_deposit, bank_account, demat, mutual_fund. Property passes by will/succession.
6. "Minor" = age < 18 on `as_of`, computed from date of birth.
7. "Knows about": owners implicitly know; others need a `knows_about` edge. Only living
   household members count toward knowledge.
8. Authentication is simulated (role switcher); one vault passphrase per family unlocks the
   server-side key. Per-member key wrapping is a productization item.
9. Checklist content is generic, India-flavoured guidance, always labelled
   "general guidance — verify with the institution or a professional".
10. PDF is generated server-side with fpdf2 (pure Python, offline); pages also have print CSS.

## 5. Risks

| Risk | Mitigation |
|------|-----------|
| Scope is large for a POV | Rules/templates table-driven; UI reuses one data hook layer |
| Windows tooling (make, Next on Windows) | Python task runner as the single source; Makefile delegates to it |
| Eval is circular (same author wrote rules and manifest) | Manifest is written from the family *stories* first; seeds include negative controls (e.g. minor nominee *with* guardian); report says so |
| Over-collection of PII by users | Input guard at API layer (not just UI), tested |
| LLM leakage | Structural-only context + guard + mock default + tests |
| Key loss | Documented: no recovery by design; encrypted export as backup |

## 6. Threat model (draft — final in docs/security.md)

Protect against: stolen SQLite file / backup (ciphertext only), tampering with stored fields or
export file (MAC), audit log edits (hash chain), over-collection (masking guard), LLM provider
seeing family data (structural-only), nominees/advisors seeing more than their scope (role views),
silent emergency access (waiting period + owner notification + cancel + audit).

Do NOT protect against (POV): compromised server while unlocked (key in memory), malicious
operator, weak passphrases beyond Argon2id cost, real authentication/identity proofing, network
attackers (no TLS locally), side channels, legal validity of emergency access, multi-device sync.
