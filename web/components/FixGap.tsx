"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import { checkFreeText } from "@/lib/masking";
import { useSession } from "@/lib/session";
import type { Gap, Item } from "@/lib/types";

import { ErrorBox, PersonSelect } from "./ui";

const DOC_NAMES: Record<string, string> = {
  policy_document: "Policy document",
  fd_receipt: "FD receipt",
  passbook: "Passbook",
  bank_statement: "Bank statement",
  demat_holding_statement: "Demat holding statement",
  cas_statement: "CAS statement",
  title_deed: "Title / sale deed",
  rc_book: "Vehicle RC",
  loan_cover_note: "Loan insurance cover note",
};

/** One-click fix shortcuts for a gap's fix_action. */
export function FixGap({ gap, people, onFixed }: { gap: Gap; people: Item[]; onFixed: () => void }) {
  const { session } = useSession();
  const [open, setOpen] = useState(false);
  const [who, setWho] = useState("");
  const [docType, setDocType] = useState(gap.fix_action.doc_types?.[0] ?? "");
  const [location, setLocation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const a = gap.fix_action;
  const token = session?.token;
  const living = people
    .filter((p) => p.props.is_alive !== false && p.props.reachable !== false)
    .map((p) => ({ id: p.id, name: String(p.props.name) }));
  const adults = people
    .filter((p) => p.props.is_alive !== false && p.inferred?.is_minor?.value !== true)
    .map((p) => ({ id: p.id, name: String(p.props.name) }));

  const LABELS: Record<string, string> = {
    add_nominee: "Add a nominee",
    replace_nominee: "Choose a new nominee",
    add_guardian: "Record a guardian",
    share_knowledge: "Mark who else knows",
    add_document: "Record where the papers are",
  };
  if (!session?.can_write || !(a.kind in LABELS)) {
    if (a.kind === "review_nominees" || a.kind === "review_date") {
      return <p className="text-sm text-muted">This needs a decision by the family — no one-click fix.</p>;
    }
    return null;
  }

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      if (a.kind === "add_nominee") {
        await api("/relations", { token, body: { src: who, rel: "nominee_of", dst: a.asset_id } });
      } else if (a.kind === "replace_nominee") {
        await api(`/relations/${encodeURIComponent(`${a.person_id}|nominee_of|${a.asset_id}`)}`, { token, method: "DELETE" });
        await api("/relations", { token, body: { src: who, rel: "nominee_of", dst: a.asset_id } });
      } else if (a.kind === "add_guardian") {
        await api("/relations", { token, body: { src: who, rel: "guardian_of", dst: a.person_id } });
      } else if (a.kind === "share_knowledge") {
        await api("/relations", { token, body: { src: who, rel: "knows_about", dst: a.asset_id } });
      } else if (a.kind === "add_document") {
        const check = checkFreeText(location);
        if (!check.ok) throw new Error(check.reason);
        const doc = await api<Item>("/documents", {
          token,
          body: { props: { doc_type: docType, label: DOC_NAMES[docType] ?? docType, location: location || undefined } },
        });
        await api("/relations", { token, body: { src: a.asset_id, rel: "documented_by", dst: doc.id } });
      }
      setOpen(false);
      onFixed();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button className="btn-primary" onClick={() => setOpen(true)}>
        {LABELS[a.kind]}
      </button>
    );
  }
  const needsPerson = a.kind !== "add_document";
  return (
    <div className="mt-2 grid gap-3 rounded-xl bg-brand-soft p-4 md:max-w-md">
      {needsPerson && (
        <PersonSelect
          label={a.kind === "add_guardian" ? "Guardian (an adult)" : a.kind === "share_knowledge" ? "Who else knows?" : "Nominee"}
          people={a.kind === "add_guardian" ? adults : living}
          exclude={[a.person_id ?? ""]}
          value={who}
          onChange={setWho}
        />
      )}
      {a.kind === "add_document" && (
        <>
          <label>
            <span className="label">Document</span>
            <select className="field" value={docType} onChange={(e) => setDocType(e.target.value)}>
              {(a.doc_types ?? []).map((d) => (
                <option key={d} value={d}>
                  {DOC_NAMES[d] ?? d}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="label">Where is it kept?</span>
            <input className="field" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="e.g. Blue file, bedroom cupboard" />
          </label>
        </>
      )}
      <ErrorBox message={error} />
      <div className="flex gap-2">
        <button className="btn-primary" disabled={busy || (needsPerson && !who)} onClick={() => void save()}>
          Save
        </button>
        <button className="btn-secondary" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </div>
  );
}
