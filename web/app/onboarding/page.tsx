"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { ItemForm, type ItemAnswer, PersonForm } from "@/components/Forms";
import { Shell } from "@/components/Shell";
import { ErrorBox, Loading, PageTitle } from "@/components/ui";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { Item, OnboardingResult, Session } from "@/lib/types";

type Msg = { from: "vault" | "you"; text: string };

const ASSET_TYPES: [string, string][] = [
  ["insurance", "Insurance policy"],
  ["bank_account", "Bank account"],
  ["fixed_deposit", "Fixed deposit"],
  ["demat", "Demat / shares"],
  ["mutual_fund", "Mutual fund"],
  ["property", "Property"],
  ["vehicle", "Vehicle"],
  ["liabilities", "Loan"],
];
const DEFAULT_DOC: Record<string, string> = {
  insurance: "policy_document", bank_account: "passbook", fixed_deposit: "fd_receipt", demat: "demat_holding_statement",
  mutual_fund: "cas_statement", property: "title_deed", vehicle: "rc_book", liabilities: "loan_agreement",
};
const INST_KIND: Record<string, string> = {
  insurance: "insurer", bank_account: "bank", fixed_deposit: "bank", demat: "depository_participant", mutual_fund: "amc",
  property: "sub_registrar", vehicle: "rto", liabilities: "bank",
};

function summarise(a: Record<string, unknown>): string {
  if (a.skip) return "Skip this section";
  if (a.done) return "That's everyone";
  if (a.yes === true) return "Yes";
  if (a.yes === false) return "No";
  if (a.name) return String(a.name) + (a.relation ? ` (${String(a.relation).replaceAll("_", " ")})` : "");
  if (a.label) return `${String(a.label)}${a.masked_id ? ` · ending ${String(a.masked_id).slice(-4)}` : ""}`;
  return "…";
}

function Conversation() {
  const { session, setSession } = useSession();
  const token = session?.token;
  const [state, setState] = useState<OnboardingResult | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api<OnboardingResult>("/onboarding", { token })
      .then((r) => {
        setState(r);
        setMsgs([{ from: "vault", text: r.question.prompt }]);
      })
      .catch((e: Error) => setError(e.message));
  }, [token]);

  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }), [msgs]);

  const send = async (answer: Record<string, unknown>) => {
    setBusy(true);
    setError(null);
    try {
      const r = await api<OnboardingResult>("/onboarding/answer", { token, body: answer });
      setMsgs((m) => [...m, { from: "you", text: summarise(answer) }, ...(r.message ? [{ from: "vault" as const, text: r.message }] : []), { from: "vault", text: r.question.prompt }]);
      setState(r);
      if (!session?.family.owner) setSession(await api<Session>("/session", { token })); // owner just created
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!state) return error ? <ErrorBox message={error} /> : <Loading />;
  const q = state.question;
  const people = q.context.people ?? [];
  const owner = session?.family.owner;

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_16rem]">
      <section className="card flex flex-col gap-4" aria-label="Conversation">
        <div className="max-h-[45vh] space-y-3 overflow-y-auto pr-1" aria-live="polite">
          {msgs.map((m, i) => (
            <p
              key={i}
              className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-lg ${m.from === "vault" ? "bg-brand-soft" : "ml-auto bg-brand text-white"}`}
            >
              {m.text}
            </p>
          ))}
          <div ref={end} />
        </div>
        <ErrorBox message={error} />
        <div className="border-t border-line pt-4">
          {q.input === "person_form" && (
            <>
              <PersonForm askRelation={!!q.context.ask_relation} busy={busy} onSubmit={(a) => void send({ ...a })} />
              {q.context.ask_relation && (
                <button className="btn-secondary mt-3" disabled={busy} onClick={() => void send({ done: true })}>
                  That&apos;s everyone — next
                </button>
              )}
            </>
          )}
          {q.input === "yesno" && (
            <div className="flex flex-wrap gap-3">
              <button className="btn-primary" disabled={busy} onClick={() => void send({ yes: true })}>
                Yes
              </button>
              <button className="btn-secondary" disabled={busy} onClick={() => void send({ yes: false })}>
                No
              </button>
            </div>
          )}
          {(q.input === "asset_form" || q.input === "liability_form") && (
            <ItemForm
              key={`${q.id}-${msgs.length}`}
              kind={q.section}
              people={people}
              ownerId={owner}
              busy={busy}
              onSubmit={(a) => void send({ ...a, has_document: a.has_document })}
            />
          )}
          {q.input === "done" && (
            <div className="flex flex-wrap gap-3">
              <Link className="btn-primary" href="/gaps">
                See the gaps we found
              </Link>
              <Link className="btn-secondary" href="/dashboard">
                Readiness score
              </Link>
            </div>
          )}
          {q.skippable && q.input !== "done" && (
            <button className="mt-3 text-base font-semibold text-brand underline" disabled={busy} onClick={() => void send({ skip: true })}>
              Skip this section
            </button>
          )}
        </div>
      </section>
      <aside className="card" aria-label="Progress">
        <p className="font-bold">
          Progress: {state.progress.percent}%
        </p>
        <div className="mt-2 h-3 rounded-full bg-line" role="progressbar" aria-valuenow={state.progress.percent} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-3 rounded-full bg-brand" style={{ width: `${state.progress.percent}%` }} />
        </div>
        <ol className="mt-4 space-y-1">
          {state.progress.sections.map((s, i) => (
            <li key={s.id} className={i === state.progress.done ? "font-bold text-brand" : i < state.progress.done ? "text-muted line-through" : ""}>
              {s.title}
              {s.skipped && <span className="ml-1 text-sm">(skipped)</span>}
            </li>
          ))}
        </ol>
      </aside>
    </div>
  );
}

function FormFallback() {
  const { session, bump } = useSession();
  const token = session?.token;
  const [kind, setKind] = useState("insurance");
  const [people, setPeople] = useState<Item[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [n, setN] = useState(0);

  useEffect(() => {
    api<Item[]>("/people", { token }).then(setPeople).catch(() => setPeople([]));
  }, [token, n]);

  const save = async (a: ItemAnswer) => {
    setError(null);
    setSaved(null);
    try {
      const isLoan = kind === "liabilities";
      const props: Record<string, unknown> = { label: a.label, masked_id: a.masked_id };
      if (isLoan) Object.assign(props, { liability_type: "loan", subtype: a.subtype });
      else Object.assign(props, { asset_type: kind, maturity_date: a.maturity_date, expiry_date: a.expiry_date });
      Object.keys(props).forEach((k) => props[k] === undefined && delete props[k]);
      const item = await api<Item>(isLoan ? "/liabilities" : "/assets", { token, body: { props } });
      const rel = (src: string, r: string, dst: string, p: Record<string, unknown> = {}) => api("/relations", { token, body: { src, rel: r, dst, props: p } });
      for (const o of a.owners) await rel(o, "owns", item.id, { role: "owner" });
      for (const o of a.co_owners) await rel(o, "owns", item.id, { role: isLoan ? "co_borrower" : "joint" });
      for (const o of a.nominees) await rel(o, "nominee_of", item.id);
      for (const o of a.knows) await rel(o, "knows_about", item.id);
      if (a.institution_name) {
        const insts = await api<Item[]>("/institutions", { token });
        let inst = insts.find((i) => String(i.props.name).toLowerCase() === a.institution_name!.toLowerCase());
        inst ??= await api<Item>("/institutions", { token, body: { props: { name: a.institution_name, kind: INST_KIND[kind] } } });
        await rel(item.id, "held_at", inst.id);
      }
      if (a.has_document) {
        const doc = await api<Item>("/documents", { token, body: { props: { doc_type: DEFAULT_DOC[kind], label: "Papers", location: a.document_location || undefined } } });
        await rel(item.id, "documented_by", doc.id);
      }
      setSaved(`Saved "${a.label}".`);
      setN((x) => x + 1);
      bump();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <section className="card grid gap-4">
      <PersonForm
        askRelation
        onSubmit={async (p) => {
          setError(null);
          try {
            await api("/people", { token, body: { props: Object.fromEntries(Object.entries(p).filter(([, v]) => v)) } });
            setSaved(`Added ${p.name}.`);
            setN((x) => x + 1);
          } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
          }
        }}
      />
      <hr className="border-line" />
      <label className="max-w-sm">
        <span className="label">What would you like to add?</span>
        <select className="field" value={kind} onChange={(e) => setKind(e.target.value)}>
          {ASSET_TYPES.map(([id, l]) => (
            <option key={id} value={id}>
              {l}
            </option>
          ))}
        </select>
      </label>
      <ErrorBox message={error} />
      {saved && (
        <p role="status" className="rounded-xl bg-brand-soft px-4 py-2 font-semibold">
          {saved}
        </p>
      )}
      <ItemForm
        key={`${kind}-${n}`}
        kind={kind}
        people={people.filter((p) => p.props.is_alive !== false).map((p) => ({ id: p.id, name: String(p.props.name) }))}
        ownerId={session?.family.owner}
        onSubmit={(a) => void save(a)}
      />
    </section>
  );
}

function Onboarding() {
  const [mode, setMode] = useState<"chat" | "form">("chat");
  return (
    <>
      <PageTitle
        title="Tell us about your family"
        sub="Answer a few simple questions. Skip anything you don't know yet — you can come back later. We only ever ask for the last 4 digits of any number."
      />
      <div role="tablist" className="mb-5 flex gap-2">
        <button role="tab" aria-selected={mode === "chat"} className={mode === "chat" ? "btn-primary" : "btn-secondary"} onClick={() => setMode("chat")}>
          Guided conversation
        </button>
        <button role="tab" aria-selected={mode === "form"} className={mode === "form" ? "btn-primary" : "btn-secondary"} onClick={() => setMode("form")}>
          I prefer a form
        </button>
      </div>
      {mode === "chat" ? <Conversation /> : <FormFallback />}
    </>
  );
}

export default function Page() {
  return (
    <Shell>
      <Onboarding />
    </Shell>
  );
}
