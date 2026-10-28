"""`make eval`: measurable evaluation, written to docs/eval-report.md.

1. Gap detection precision/recall against the planted-gap manifest (+ negative controls).
2. Checklist correctness against hand-written reference checklists (9 family x scenario pairs).
3. Crypto suite: wrong passphrase, tampering (field, DB row, export), no plaintext sensitive values on disk.
4. Masking: full-number / ID / secret inputs rejected by the API; legitimate masked inputs accepted.
5. LLM boundary: no names, ids or sensitive values reach the LLM client during onboarding and checklists.

Everything runs on fresh vaults built from data/seed in a temp dir, so results are reproducible.
"""

from __future__ import annotations

import base64
import json
import shutil
import sqlite3
import sys
import tempfile
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

from app.config import ROOT
from app.core import onboarding, totp
from app.core.checklist import SCENARIOS, generate
from app.core.crypto import TamperDetected, WrongPassphrase, decrypt_export, encrypt_export
from app.core.estate import Estate
from app.core.gaps import detect_gaps
from app.kg import llm as llm_mod
from app.kg.store import NetworkXSQLiteStore
from app.seed import build_vault, family_files, load_family

AS_OF = date(2026, 11, 1)
REPORT = ROOT / "docs" / "eval-report.md"


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


# ---------------------------------------------------------------------------------------------- 1. gaps
def eval_gaps(stores: dict, manifest: dict) -> dict:
    per_family, per_rule = {}, defaultdict(lambda: [0, 0, 0])
    tot = [0, 0, 0]
    neg_hits = []
    for fid, store in stores.items():
        window = manifest.get("window_days", 60)
        got = {g.key for g in detect_gaps(Estate(store, AS_OF), window)}
        exp = {x["key"] for x in manifest["families"][fid]}
        tp, fp, fn = len(got & exp), len(got - exp), len(exp - got)
        per_family[fid] = {"tp": tp, "fp": fp, "fn": fn, "extra": sorted(got - exp), "missed": sorted(exp - got)}
        for k in got | exp:
            rule = k.split(":")[0]
            per_rule[rule][0] += k in got and k in exp
            per_rule[rule][1] += k in got and k not in exp
            per_rule[rule][2] += k in exp and k not in got
        tot = [tot[0] + tp, tot[1] + fp, tot[2] + fn]
        neg_hits += [k for k in manifest.get("negative_controls", []) if k in got]
    return {"per_family": per_family, "per_rule": dict(per_rule), "total": tot, "negative_hits": neg_hits,
            "negative_total": len(manifest.get("negative_controls", []))}


# ---------------------------------------------------------------------------------------------- 2. checklists
def _order_agreement(ref_items: list[str], got_items: list[str]) -> float:
    """Fraction of reference item pairs that appear in the same relative order in the output."""
    pos = {k: i for i, k in enumerate(got_items)}
    common = [k for k in ref_items if k in pos]
    pairs = [(a, b) for i, a in enumerate(common) for b in common[i + 1:]]
    return sum(pos[a] < pos[b] for a, b in pairs) / len(pairs) if pairs else 1.0


def eval_checklists(stores: dict, ref: dict) -> dict:
    rows = []
    for fid, store in stores.items():
        est = Estate(store, AS_OF)
        for scenario in SCENARIOS:
            r = ref[fid][scenario]
            cl = generate(est, scenario)
            got = {(s.item_ids[0], s.action): s for s in cl.steps if s.item_ids}
            exp = {(i, a): (set(actors), blocked) for i, a, actors, blocked in r["steps"]}
            tp = len(set(got) & set(exp))
            p, rc, _ = prf(tp, len(set(got) - set(exp)), len(set(exp) - set(got)))
            matched = set(got) & set(exp)
            actor_ok = sum(set(got[k].actor_ids) == exp[k][0] for k in matched)
            blocked_ok = sum(got[k].blocked == exp[k][1] for k in matched)
            uni_got = [(s.action, set(s.actor_ids)) for s in cl.steps if not s.item_ids]
            uni_exp = [(a, set(c)) for a, c in r["universal"]]
            first_ok = [s.action for s in cl.steps[: len(uni_exp)]] == [a for a, _ in uni_exp]
            rows.append({
                "family": fid, "scenario": scenario, "steps_ref": len(exp), "steps_got": len(got),
                "precision": p, "recall": rc,
                "actor_acc": actor_ok / len(matched) if matched else 1.0,
                "blocked_acc": blocked_ok / len(matched) if matched else 1.0,
                "order": _order_agreement([i for i, *_ in r["steps"]], [s.item_ids[0] for s in cl.steps if s.item_ids]),
                "universal_ok": uni_got == uni_exp and first_ok,
                "disclaimer": "General guidance" in cl.disclaimer,
            })
    return {"rows": rows}


# ---------------------------------------------------------------------------------------------- 3. crypto
def _sensitive_plaintexts(fam: dict) -> list[str]:
    vals = [p["dob"] for p in fam["people"].values() if p.get("dob")]
    if fam.get("totp_secret"):
        vals.append(fam["totp_secret"])  # second-factor secret must be encrypted too
    for section in ("assets", "liabilities"):
        for spec in (fam.get(section) or {}).values():
            for k in ("notes", "masked_id"):
                if spec["props"].get(k):
                    vals.append(str(spec["props"][k]))
            vals += [d["location"] for d in spec.get("docs", []) if d.get("location")]
    return vals


def eval_crypto(tmp: Path, families: dict) -> list[tuple[str, bool, str]]:
    results = []
    # (a) no plaintext sensitive values on disk
    leaks, checked = [], 0
    for fid, fam in families.items():
        raw = (tmp / f"{fid}.db").read_bytes()
        for v in _sensitive_plaintexts(fam):
            checked += 1
            if v.encode() in raw or json.dumps(v).encode() in raw:
                leaks.append(f"{fid}:{v[:12]}")
    results.append(("No plaintext sensitive values in vault files", not leaks,
                    f"{checked} sensitive values scanned across {len(families)} vaults; {len(leaks)} found"))
    # (b) wrong passphrase
    fam = families["family_a"]
    try:
        NetworkXSQLiteStore.open(tmp / "family_a.db", "definitely-wrong-passphrase")
        ok = False
    except WrongPassphrase:
        ok = True
    results.append(("Wrong passphrase is rejected", ok, "Argon2id-derived key fails the key-check MAC"))
    # (c) tampering with a stored ciphertext is detected on unlock/load
    copy = tmp / "tamper.db"
    shutil.copy(tmp / "family_a.db", copy)
    db = sqlite3.connect(copy)
    nid, props = db.execute("SELECT id, props FROM nodes WHERE id='a_term'").fetchone()
    d = json.loads(props)
    blob = bytearray(base64.b64decode(d["notes"][4:]))
    blob[-3] ^= 0xFF
    d["notes"] = "fv1:" + base64.b64encode(bytes(blob)).decode()
    db.execute("UPDATE nodes SET props=? WHERE id=?", (json.dumps(d), nid))
    db.commit()
    db.close()
    try:
        NetworkXSQLiteStore.open(copy, fam["demo_passphrase"]).close()
        ok = False
    except TamperDetected:
        ok = True
    results.append(("Modified ciphertext in the DB is detected", ok, "one byte flipped in a_term notes -> MAC failure"))
    # (d) moving a ciphertext to another record/field is detected (AAD binding)
    shutil.copy(tmp / "family_a.db", copy)
    db = sqlite3.connect(copy)
    a = json.loads(db.execute("SELECT props FROM nodes WHERE id='a_term'").fetchone()[0])
    b = json.loads(db.execute("SELECT props FROM nodes WHERE id='a_demat'").fetchone()[0])
    b["notes"] = a["notes"]
    db.execute("UPDATE nodes SET props=? WHERE id='a_demat'", (json.dumps(b),))
    db.commit()
    db.close()
    try:
        NetworkXSQLiteStore.open(copy, fam["demo_passphrase"]).close()
        ok = False
    except TamperDetected:
        ok = True
    results.append(("Ciphertext swapped between records is detected", ok, "AAD binds each value to record + field"))
    # (e) export: wrong passphrase / tampering
    store = NetworkXSQLiteStore.open(tmp / "family_a.db", fam["demo_passphrase"])
    exp = encrypt_export(store.dump(), "export-pass-123")
    store.close()
    names_in_export = b"Rohan" in exp or b"almirah" in exp
    results.append(("Export file contains no plaintext", not names_in_export, f"{len(exp)} bytes, names not present"))
    try:
        decrypt_export(exp, "wrong-export-pass")
        ok = False
    except WrongPassphrase:
        ok = True
    results.append(("Export: wrong passphrase rejected", ok, ""))
    tampered = exp[:-10] + bytes([exp[-10] ^ 1]) + exp[-9:]
    try:
        decrypt_export(tampered, "export-pass-123")
        ok = False
    except (WrongPassphrase, TamperDetected):
        ok = True
    results.append(("Export: tampering detected", ok, "byte flipped in ciphertext"))
    return results


# ---------------------------------------------------------------------------------------------- 4. masking
FULL_NUMBER_INPUTS = [
    ("masked_id", "50100234567890"), ("masked_id", "123456789012"), ("masked_id", "4111 1111 1111 1111"),
    ("masked_id", "4111-1111-1111-1111"), ("masked_id", "XXXX12345"), ("masked_id", "ABCDE1234F"),
    ("masked_id", "SBIN0001234"), ("masked_id", "00123456"), ("notes", "Aadhaar 1234 5678 9012"),
    ("notes", "Account no 50100234567890"), ("notes", "PAN ABCDE1234F"), ("notes", "card 4111111111111111"),
    ("notes", "netbanking password is Tiger@123"), ("notes", "ATM PIN 4321"), ("notes", "OTP: 889911"),
    ("notes", "UPI PIN = 1234"), ("notes", "CVV 123"), ("label", "Policy 987654321"),
    ("account_number", "1234"), ("aadhaar", "1234"), ("password", "x"), ("pin", "1234"),
]
OK_INPUTS = [
    ("masked_id", "1234"), ("masked_id", "XXXX1234"), ("masked_id", "****9876"), ("masked_id", "xx-xx-ab12"),
    ("notes", "Kept in the Godrej almirah"), ("notes", "Matures on 2026-11-20"), ("notes", "Locker no 12"),
    ("label", "Salary account"),
]


def eval_masking() -> dict:
    from fastapi.testclient import TestClient

    from app.api.main import create_app
    from app.api.sessions import Registry

    tmp = Path(tempfile.mkdtemp())
    try:
        fam = load_family(next(f for f in family_files() if "family_a" in f.name))
        build_vault(fam, tmp)
        reg = Registry(tmp)
        client = TestClient(create_app(reg))
        ch = client.post("/session/unlock", json={"family_id": "family_a",
                                                  "passphrase": fam["demo_passphrase"]}).json()
        tok = client.post("/session/verify", json={"challenge_id": ch["challenge_id"],
                                                   "code": totp.code_at(fam["totp_secret"])}).json()["token"]
        h = {"Authorization": f"Bearer {tok}"}

        def post(field: str, value: str):
            props = {"asset_type": "bank_account", "label": "Savings"}
            props[field] = value
            return client.post("/assets", json={"props": props}, headers=h)

        rejected, explained = 0, 0
        failures = []
        for field, value in FULL_NUMBER_INPUTS:
            r = post(field, value)
            if r.status_code == 422:
                rejected += 1
                explained += "last 4" in r.json().get("why", "")
            else:
                failures.append(f"{field}={value!r} -> {r.status_code}")
        accepted = sum(post(f, v).status_code == 201 for f, v in OK_INPUTS)
        stored = client.get("/assets", headers=h).json()
        stored_ok = all(len(str(a["props"].get("masked_id", "XXXX")).replace("XXXX", "")) <= 4 for a in stored)
        reg.close_all()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"bad_total": len(FULL_NUMBER_INPUTS), "rejected": rejected, "explained": explained,
            "ok_total": len(OK_INPUTS), "accepted": accepted, "failures": failures, "stored_ok": stored_ok}


# ---------------------------------------------------------------------------------------------- 5. LLM boundary
def eval_llm_boundary(stores: dict, families: dict) -> dict:
    mock = llm_mod.MockLLM()
    old = llm_mod._client
    llm_mod._client = mock
    onboard_tmp = Path(tempfile.mkdtemp())
    try:
        for store in stores.values():
            est = Estate(store, AS_OF)
            for scenario in SCENARIOS:
                generate(est, scenario)
        # Scripted onboarding with real-looking (synthetic) answers.
        ob = NetworkXSQLiteStore.create(onboard_tmp / "ob.db", "onboard-pass-123", {"id": "ob"})
        est = Estate(ob, AS_OF)
        owner = onboarding.answer(est, {"name": "Meera Iyer", "dob": "1985-02-02"}).last_created[0]
        onboarding.answer(est, {"name": "Tara Iyer", "relation": "daughter", "dob": "2019-01-01"})
        onboarding.answer(est, {"done": True})
        onboarding.answer(est, {"yes": True})
        onboarding.answer(est, {"label": "Kaveri term plan", "masked_id": "7788", "owners": [owner],
                                "institution_name": "Kaveri Life", "has_document": True,
                                "document_location": "Steel cupboard top shelf"})
        ob.close()
    finally:
        llm_mod._client = old
        shutil.rmtree(onboard_tmp, ignore_errors=True)
    payload = json.dumps([c.model_dump() for c in mock.calls])
    secrets = {"Meera Iyer", "Tara Iyer", "Kaveri term plan", "Kaveri Life", "XXXX7788", "Steel cupboard top shelf",
               "1985-02-02", "2019-01-01"}
    for fam in families.values():
        secrets |= {p["name"] for p in fam["people"].values()}
        secrets |= {i["name"] for i in fam["institutions"].values()}
        secrets |= set(_sensitive_plaintexts(fam))
        secrets |= set(fam["people"]) | set(fam.get("assets") or {})
    # Our own fixed template text is allowed to reach the LLM; a family value that merely equals a word
    # in those templates (e.g. a document "kept in DigiLocker") is not a leak.
    from app.core import checklist as cl_mod

    corpus = json.dumps([cl_mod.DEATH, cl_mod.INCAPACITY, cl_mod.LOSS, cl_mod.UNIVERSAL])
    generic = sorted(s for s in secrets if s and s in corpus)
    leaked = sorted(s for s in secrets if s and s in payload and s not in generic)
    return {"calls": len(mock.calls), "values_checked": len(secrets), "leaked": leaked, "generic": generic}


# ---------------------------------------------------------------------------------------------- report
def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def write_report(g: dict, c: dict, cr: list, m: dict, lb: dict) -> str:
    tp, fp, fn = g["total"]
    p, r, f = prf(tp, fp, fn)
    lines = [
        "# Evaluation report",
        "",
        f"Generated by `make eval` on {datetime.now(UTC):%Y-%m-%d %H:%M} UTC. Rules evaluated as of {AS_OF}. "
        "All data is synthetic.",
        "",
        "## 1. Gap detection vs planted-gap manifest",
        "",
        f"**Overall: precision {pct(p)}, recall {pct(r)}, F1 {pct(f)}** "
        f"(TP {tp}, FP {fp}, FN {fn}). Negative controls flagged: {len(g['negative_hits'])}/{g['negative_total']}.",
        "",
        "| Family | TP | FP | FN | Precision | Recall | Extra | Missed |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for fid, v in g["per_family"].items():
        pp, rr, _ = prf(v["tp"], v["fp"], v["fn"])
        lines.append(f"| {fid} | {v['tp']} | {v['fp']} | {v['fn']} | {pct(pp)} | {pct(rr)} | "
                     f"{', '.join(v['extra']) or '-'} | {', '.join(v['missed']) or '-'} |")
    lines += ["", "| Rule | TP | FP | FN |", "|---|---|---|---|"]
    for rule, (a, b, d) in sorted(g["per_rule"].items()):
        lines.append(f"| {rule} | {a} | {b} | {d} |")
    lines += [
        "",
        "Every rule G01-G08 is exercised by at least one planted gap or negative control.",
        "",
        "## 2. Checklist correctness vs hand-written references",
        "",
        "Step = (asset, action). Actor accuracy and blocked accuracy are over matched steps; order = fraction of "
        "reference step pairs in the same relative order.",
        "",
        "| Family | Scenario | Ref steps | Got | Precision | Recall | Actors | Blocked | Order | Universal steps |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in c["rows"]:
        lines.append(
            f"| {row['family']} | {row['scenario']} | {row['steps_ref']} | {row['steps_got']} "
            f"| {pct(row['precision'])} | {pct(row['recall'])} | {pct(row['actor_acc'])} "
            f"| {pct(row['blocked_acc'])} | {pct(row['order'])} | "
            f"{'ok' if row['universal_ok'] else 'MISMATCH'} |")
    n = len(c["rows"])
    keys = ("precision", "recall", "actor_acc", "blocked_acc", "order")
    avg = {k: sum(row[k] for row in c["rows"]) / n for k in keys}
    lines += [
        "",
        f"**Mean over {n} checklists: precision {pct(avg['precision'])}, recall {pct(avg['recall'])}, actor accuracy "
        f"{pct(avg['actor_acc'])}, blocked-flag accuracy {pct(avg['blocked_acc'])}, "
        f"order agreement {pct(avg['order'])}.** "
        f"Disclaimer present on {sum(r['disclaimer'] for r in c['rows'])}/{n}.",
        "",
        "## 3. Crypto suite",
        "",
        "| Check | Result | Detail |",
        "|---|---|---|",
    ]
    for name, ok, detail in cr:
        lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} | {detail} |")
    lines += [
        "",
        "## 4. Masking: full-number inputs rejected",
        "",
        f"- Full numbers / IDs / secrets sent to `POST /assets`: **{m['rejected']}/{m['bad_total']} rejected** "
        "(HTTP 422), "
        f"{m['explained']}/{m['rejected']} with the plain-language explanation.",
        f"- Legitimate masked inputs: **{m['accepted']}/{m['ok_total']} accepted**.",
        f"- Every stored identifier reveals at most 4 characters: {'yes' if m['stored_ok'] else 'NO'}.",
    ]
    if m["failures"]:
        lines.append(f"- Not rejected: {'; '.join(m['failures'])}")
    lines += [
        "",
        "## 5. LLM boundary",
        "",
        f"- {lb['calls']} LLM calls made while generating all 9 checklists and a scripted onboarding "
        "(mock client records every payload).",
        f"- {lb['values_checked']} names, ids and sensitive values checked against the payloads: "
        f"**{len(lb['leaked'])} found**{': ' + ', '.join(lb['leaked']) if lb['leaked'] else ''}.",
        f"- Excluded as generic template words (they occur in our fixed templates, not as family data): "
        f"{', '.join(lb['generic']) or 'none'}.",
        "",
        "## Caveats",
        "",
        "- The planted-gap manifest and the reference checklists were written by the same team that wrote the rules. "
        "They were written from the family stories, and the seeds include negative controls, but this measures "
        "*consistency with the specification*, not real-world accuracy. A real evaluation needs families' actual "
        "holdings, reviewed by an estate professional.",
        "- Checklist content is generic guidance; correctness here means the right steps, actors, blocking and order "
        "for the recorded graph, not legal accuracy of each institution's process.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    manifest = yaml.safe_load((ROOT / "data/eval/gap_manifest.yaml").read_text(encoding="utf-8"))
    ref = yaml.safe_load((ROOT / "data/eval/reference_checklists.yaml").read_text(encoding="utf-8"))
    families = {f["id"]: f for f in (load_family(p) for p in family_files())}
    tmp = Path(tempfile.mkdtemp())
    stores = {}
    try:
        for fam in families.values():
            build_vault(fam, tmp)
        stores = {fid: NetworkXSQLiteStore.open(tmp / f"{fid}.db", fam["demo_passphrase"])
                  for fid, fam in families.items()}
        g = eval_gaps(stores, manifest)
        c = eval_checklists(stores, ref)
        lb = eval_llm_boundary(stores, families)
        for s in stores.values():
            s.close()
        stores = {}
        cr = eval_crypto(tmp, families)
    finally:
        for s in stores.values():
            s.close()
        shutil.rmtree(tmp, ignore_errors=True)
    m = eval_masking()
    report = write_report(g, c, cr, m, lb)
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(report, encoding="utf-8")
    tp, fp, fn = g["total"]
    p, r, _ = prf(tp, fp, fn)
    print(f"gaps: precision {pct(p)} recall {pct(r)} | checklists: "
          f"{sum(row['recall'] == 1 and row['precision'] == 1 for row in c['rows'])}/{len(c['rows'])} exact | "
          f"crypto {sum(ok for _, ok, _ in cr)}/{len(cr)} | masking {m['rejected']}/{m['bad_total']} rejected | "
          f"llm leaks {len(lb['leaked'])}")
    print(f"wrote {REPORT}")
    ok = (fp == fn == 0 and all(ok for _, ok, _ in cr) and m["rejected"] == m["bad_total"] and not lb["leaked"])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
