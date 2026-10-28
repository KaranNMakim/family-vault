# Security and threat model (POV)

> This is a **demo**. It handles synthetic data only. Do not use it for real sensitive data. The web app shows a
> permanent banner saying so.

## Data minimisation first

The best protection is not holding the data. family-vault records **where** things are and **who** is involved —
never the secrets needed to operate an account.

- Identifiers are stored **masked, last 4 characters only** (`XXXX1234`). The API rejects (HTTP 422, with a plain-language
  reason) any identifier revealing more than 4 characters.
- Free-text fields (labels, notes, document locations, names) are rejected if they contain long digit runs
  (account/card numbers), Aadhaar-like or PAN-like values, or a password/PIN/OTP/CVV with a value.
- Payload keys such as `password`, `pin`, `otp`, `cvv`, `account_number`, `card_number`, `aadhaar`, `pan`, `passport`
  are rejected anywhere in any JSON body.
- No phone numbers or email addresses are collected; "reachable" is a yes/no flag.
- The same checks run in the browser (`web/lib/masking.ts`) for instant feedback, but the API is the enforcement point.

## Encryption

| Item | Design |
|---|---|
| Key derivation | Argon2id (libsodium `crypto_pwhash`, INTERACTIVE limits: 2 ops, 64 MiB), random 16-byte salt per vault |
| Field encryption | XChaCha20-Poly1305 (IETF AEAD), random 24-byte nonce per value |
| Binding | Associated data = `record_id:field`, so ciphertexts cannot be moved between records/fields undetected |
| What is encrypted | Every property marked `sensitive: true` in `app/kg/ontology.yaml`: dates of birth, masked ids, notes, document locations |
| Stored with the vault | KDF salt and parameters, and a key-check ciphertext. **The key and passphrase are never stored.** |
| Export | Whole vault serialised and sealed with a key derived from a separate export passphrase; header authenticated as AAD |

Non-sensitive structure (names, asset types, institution names, relationships) is stored in plaintext so the demo
can list families before unlock and keep the graph queryable. A production design would encrypt more (see below).

### Key loss

There is **no recovery** if the passphrase is lost: the vault cannot be decrypted by anyone, including the operator.
This is deliberate. Mitigations for the POV: keep an encrypted export (with a different passphrase) somewhere safe.
A product would add recovery kits (e.g. Shamir shares held by family members) and per-member key wrapping.

## Unlocking: two-step verification

1. **Passphrase** — derives the vault key with Argon2id and opens the vault. Wrong passphrases are counted per vault:
   5 failures in 15 minutes lock the vault for 5 minutes (HTTP 429 with `Retry-After`). Failures are written to the
   audit log even though the vault is still locked.
2. **Authenticator code** — a 6-digit TOTP (RFC 6238: HMAC-SHA1, 30-second steps, ±1 step of clock drift), compatible
   with Google Authenticator, Microsoft Authenticator and Authy. The shared secret is stored **inside the vault,
   encrypted with the vault key**, so it can only be checked after step 1. Each challenge expires after 5 minutes and
   allows 5 tries; a used code cannot be replayed.

Only after both steps is a session token issued. Sessions expire after 15 minutes idle (the web app also auto-locks)
or 8 hours in total. New and imported vaults enrol a fresh authenticator key (shown once with an `otpauth://` URI).
For the sample families the setup keys are published on purpose, and the start page shows a *demo authenticator*
that stands in for the phone app.

## Access control

Every API response is filtered server-side by the caller's role:

| Role | Sees | Can change |
|---|---|---|
| Owner | Everything, audit log, export | Everything |
| Spouse (full) | Everything | Everything |
| Spouse (shared) | Assets they own, co-own, are nominee of, or know about | Nothing |
| Nominee | Only assets where they are nominee, plus institution and document location; no private notes, no other people's dates of birth, no "who knows" | Nothing |
| Advisor | Only assets `advised_by` them; all sensitive fields hidden | Nothing |
| Emergency grantee | Nominee scope, only while an activated request is within its 7-day window | Nothing |

Minors cannot file emergency-access requests (their guardian should).

## Emergency access (simulated)

Request → owner notified immediately → configurable waiting period (default 72 h) during which the owner can cancel →
after the delay the request can be activated → read-only nominee-scope view for 7 days → automatic expiry. Every
transition is written to the audit log. The clock is simulated for demos.

## Audit

Append-only log in the vault: each entry stores `sha256(prev_hash + entry)`. Editing or deleting any entry breaks the
chain; `GET /audit` reports whether the chain verifies. Details are redacted before writing (sensitive keys removed,
long digit runs scrubbed). Logged: unlocks, role switches, list/view of entities, graph and checklist views, every
change, emergency transitions, exports and imports.

## LLM boundary

The LLM is optional (`LLM_MODE=live`) and only rewrites wording. It receives a `StructuralContext`: whitelisted keys
(section, slot, asset type, action, counts, our own template text with `{placeholders}`). A guard rejects any value
with 3+ consecutive digits or non-whitelisted keys. Real names and values are substituted **after** the LLM call, and
a reply that drops a placeholder is discarded. Gap detection, scoring and checklists never use the LLM. The eval
checks every recorded LLM payload for names, ids and sensitive values (result: 0 found).

## Logging

Structured JSON logs; values under sensitive keys are replaced with `[REDACTED]` and digit runs of 5+ are scrubbed.

## Threat model

**Protects against (in this POV):**

- Theft of a vault file, backup or export → sensitive fields and exports are ciphertext; an Argon2id-hardened passphrase is needed.
- Tampering with stored values or exports → AEAD authentication fails; record/field binding stops swapping.
- Tampering with the audit log → hash chain breaks.
- Over-collection (users typing full account numbers, Aadhaar, passwords) → rejected at the API with an explanation.
- The LLM provider seeing family data → structural-only context plus guard; mock by default.
- Nominees/advisors seeing more than their scope → server-side role filtering on every endpoint.
- Silent emergency access → waiting period, owner notification, cancel, expiry and audit.

**Does NOT protect against (out of scope for the POV):**

- A compromised server while a vault is unlocked (the key is in process memory), or a malicious operator.
- Weak passphrases beyond what Argon2id cost buys; no passphrase-strength enforcement beyond 8 characters.
- Per-person identity: the owner unlocks with passphrase + TOTP, but other family roles are previewed through a demo
  role switcher, not separate logins with their own keys. No phishing-resistant factor (passkeys/WebAuthn) yet.
- Network attackers: the demo runs over plain HTTP on localhost; CORS allows any localhost origin.
- Metadata: names, relationships, institution names and asset types are plaintext in the vault file.
- Side channels, browser compromise, shoulder-surfing, malicious browser extensions.
- Legal validity of emergency access, nominations or checklists.
- Concurrency and multi-device sync (single process, SQLite).
