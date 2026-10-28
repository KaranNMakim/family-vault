"use client";

import { useState } from "react";

import { checkFreeText, checkMaskedId, WHY } from "@/lib/masking";
import type { Ref } from "@/lib/types";

export const RELATIONS = [
  "spouse", "son", "daughter", "father", "mother", "brother", "sister", "grandson", "granddaughter", "grandfather",
  "grandmother", "daughter_in_law", "son_in_law", "father_in_law", "mother_in_law", "nephew", "niece", "friend", "other",
];

export interface PersonAnswer {
  name: string;
  relation?: string;
  dob?: string;
}

export function PersonForm({ askRelation, onSubmit, busy }: { askRelation: boolean; onSubmit: (a: PersonAnswer) => void; busy?: boolean }) {
  const [name, setName] = useState("");
  const [relation, setRelation] = useState("spouse");
  const [dob, setDob] = useState("");
  const nameCheck = checkFreeText(name);
  return (
    <form
      className="grid gap-3 md:grid-cols-3"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ name, relation: askRelation ? relation : undefined, dob: dob || undefined });
        setName("");
        setDob("");
      }}
    >
      <label>
        <span className="label">Name</span>
        <input className="field" value={name} onChange={(e) => setName(e.target.value)} required />
        {!nameCheck.ok && <span className="text-sm text-sev-critical">{nameCheck.reason}</span>}
      </label>
      {askRelation && (
        <label>
          <span className="label">Relation to you</span>
          <select className="field" value={relation} onChange={(e) => setRelation(e.target.value)}>
            {RELATIONS.map((r) => (
              <option key={r} value={r}>
                {r.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </label>
      )}
      <label>
        <span className="label">Date of birth (optional)</span>
        <input className="field" type="date" value={dob} onChange={(e) => setDob(e.target.value)} />
        <span className="text-sm text-muted">Only used to spot minors who need a guardian.</span>
      </label>
      <div className="md:col-span-3">
        <button className="btn-primary" disabled={busy || !name || !nameCheck.ok}>
          {askRelation ? "Add this person" : "Continue"}
        </button>
      </div>
    </form>
  );
}

export interface ItemAnswer {
  label: string;
  institution_name?: string;
  masked_id?: string;
  maturity_date?: string;
  expiry_date?: string;
  owners: string[];
  co_owners: string[];
  nominees: string[];
  knows: string[];
  has_document: boolean;
  document_location?: string;
  subtype?: string;
}

function PeopleChecks({ label, people, value, onChange, hint }: { label: string; people: Ref[]; value: string[]; onChange: (v: string[]) => void; hint?: string }) {
  return (
    <fieldset>
      <legend className="label">{label}</legend>
      {hint && <p className="-mt-1 mb-1 text-sm text-muted">{hint}</p>}
      <div className="flex flex-wrap gap-2">
        {people.map((p) => {
          const on = value.includes(p.id);
          return (
            <label key={p.id} className={`chip cursor-pointer border px-3 py-1.5 text-base ${on ? "border-brand bg-brand-soft" : "border-line bg-card"}`}>
              <input
                type="checkbox"
                className="mr-2 size-4"
                checked={on}
                onChange={() => onChange(on ? value.filter((x) => x !== p.id) : [...value, p.id])}
              />
              {p.name}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

export function ItemForm({
  kind,
  people,
  ownerId,
  onSubmit,
  busy,
}: {
  kind: string; // asset type or "liabilities"
  people: Ref[];
  ownerId?: string;
  onSubmit: (a: ItemAnswer) => void;
  busy?: boolean;
}) {
  const isLoan = kind === "liabilities";
  const [a, setA] = useState<ItemAnswer>({
    label: "",
    owners: ownerId ? [ownerId] : [],
    co_owners: [],
    nominees: [],
    knows: [],
    has_document: false,
    subtype: "home_loan",
  });
  const set = (patch: Partial<ItemAnswer>) => setA((x) => ({ ...x, ...patch }));
  const mid = checkMaskedId(a.masked_id ?? "");
  const loc = checkFreeText(a.document_location ?? "");
  const lbl = checkFreeText(a.label);
  const ok = a.label && mid.ok && loc.ok && lbl.ok && a.owners.length > 0;
  const dated = kind === "fixed_deposit" || kind === "insurance";
  const nominable = ["insurance", "fixed_deposit", "bank_account", "demat", "mutual_fund"].includes(kind);

  return (
    <form
      className="grid gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ ...a, masked_id: mid.ok && mid.value ? mid.value : undefined });
      }}
    >
      <div className="grid gap-3 md:grid-cols-2">
        <label>
          <span className="label">A friendly name</span>
          <input className="field" value={a.label} onChange={(e) => set({ label: e.target.value })} placeholder={isLoan ? "e.g. Home loan" : "e.g. Term plan, Salary account"} required />
          {!lbl.ok && <span className="text-sm text-sev-critical">{lbl.reason}</span>}
        </label>
        <label>
          <span className="label">{isLoan ? "Lender" : "Bank / insurer / company"}</span>
          <input className="field" value={a.institution_name ?? ""} onChange={(e) => set({ institution_name: e.target.value })} />
        </label>
        <label>
          <span className="label">Last 4 digits of the number</span>
          <input className="field" inputMode="text" maxLength={20} value={a.masked_id ?? ""} onChange={(e) => set({ masked_id: e.target.value })} placeholder="e.g. 4471" aria-describedby="mid-help" />
          <span id="mid-help" className={`text-sm ${mid.ok ? "text-muted" : "font-semibold text-sev-critical"}`}>
            {mid.ok ? "Only the last 4 — never the full number." : `${mid.reason} ${WHY}`}
          </span>
        </label>
        {dated && (
          <label>
            <span className="label">{kind === "fixed_deposit" ? "Maturity date" : "Cover ends / renewal date"}</span>
            <input
              className="field"
              type="date"
              value={(kind === "fixed_deposit" ? a.maturity_date : a.expiry_date) ?? ""}
              onChange={(e) => set(kind === "fixed_deposit" ? { maturity_date: e.target.value } : { expiry_date: e.target.value })}
            />
          </label>
        )}
        {isLoan && (
          <label>
            <span className="label">Kind of loan</span>
            <select className="field" value={a.subtype} onChange={(e) => set({ subtype: e.target.value })}>
              {["home_loan", "vehicle_loan", "personal_loan", "education_loan", "gold_loan", "other"].map((s) => (
                <option key={s} value={s}>
                  {s.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <PeopleChecks label={isLoan ? "Borrower" : "Whose is it?"} people={people} value={a.owners} onChange={(v) => set({ owners: v })} />
      <PeopleChecks
        label={isLoan ? "Co-borrower (if any)" : "Joint holder (if any)"}
        people={people.filter((p) => !a.owners.includes(p.id))}
        value={a.co_owners}
        onChange={(v) => set({ co_owners: v })}
      />
      {nominable && (
        <PeopleChecks label="Nominee" hint="The person registered with the institution to receive it." people={people} value={a.nominees} onChange={(v) => set({ nominees: v })} />
      )}
      <PeopleChecks
        label="Who else in the family knows this exists?"
        people={people.filter((p) => !a.owners.includes(p.id))}
        value={a.knows}
        onChange={(v) => set({ knows: v })}
      />
      <label className="flex items-center gap-2">
        <input type="checkbox" className="size-5" checked={a.has_document} onChange={(e) => set({ has_document: e.target.checked })} />
        I know where the papers are
      </label>
      {a.has_document && (
        <label>
          <span className="label">Where are they kept?</span>
          <input className="field" value={a.document_location ?? ""} onChange={(e) => set({ document_location: e.target.value })} placeholder="e.g. Blue file in bedroom cupboard" />
          {!loc.ok && <span className="text-sm text-sev-critical">{loc.reason}</span>}
        </label>
      )}
      <div>
        <button className="btn-primary" disabled={busy || !ok}>
          Save
        </button>
      </div>
    </form>
  );
}
