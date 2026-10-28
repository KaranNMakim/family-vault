"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ErrorBox } from "@/components/ui";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { FamilyMeta, Session } from "@/lib/types";

/** Synthetic demo vaults only. These passphrases protect fictional data and are published on purpose. */
const DEMO_PASSPHRASES: Record<string, string> = {
  family_a: "mehta-demo-vault",
  family_b: "agarwal-demo-vault",
  family_c: "nair-demo-vault",
};

function FamilyCard({ fam, onUnlocked }: { fam: FamilyMeta; onUnlocked: (s: Session) => void }) {
  const [pass, setPass] = useState(DEMO_PASSPHRASES[fam.id] ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      className="card flex flex-col gap-3"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        try {
          onUnlocked(await api<Session>("/session/unlock", { body: { family_id: fam.id, passphrase: pass } }));
        } catch (err) {
          setError(err instanceof Error ? err.message : String(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      <h3 className="text-xl font-bold">{fam.display_name}</h3>
      {fam.story && <p className="text-base text-muted">{fam.story}</p>}
      <label>
        <span className="label">Vault passphrase</span>
        <input className="field" type="password" value={pass} onChange={(e) => setPass(e.target.value)} autoComplete="off" />
        {DEMO_PASSPHRASES[fam.id] && <span className="text-sm text-muted">Demo passphrase pre-filled.</span>}
      </label>
      <ErrorBox message={error} />
      <button className="btn-primary mt-auto" disabled={busy || pass.length < 8}>
        {busy ? "Unlocking…" : "Open this family's vault"}
      </button>
    </form>
  );
}

function NewFamily({ onCreated }: { onCreated: (s: Session) => void }) {
  const [name, setName] = useState("");
  const [pass, setPass] = useState("");
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      className="card flex flex-col gap-3"
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        try {
          onCreated(await api<Session>("/vaults", { body: { display_name: name, passphrase: pass } }));
        } catch (err) {
          setError(err instanceof Error ? err.message : String(err));
        }
      }}
    >
      <h3 className="text-xl font-bold">Start a new family</h3>
      <p className="text-base text-muted">A guided conversation builds your family map step by step. Takes about 5 minutes.</p>
      <label>
        <span className="label">Family name</span>
        <input className="field" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Iyer family" />
      </label>
      <label>
        <span className="label">Choose a passphrase (8+ characters)</span>
        <input className="field" type="password" value={pass} onChange={(e) => setPass(e.target.value)} autoComplete="new-password" />
        <span className="text-sm text-muted">
          It is never stored. If you forget it, the vault cannot be opened — keep an encrypted export as a backup.
        </span>
      </label>
      <ErrorBox message={error} />
      <button className="btn-primary mt-auto" disabled={!name || pass.length < 8}>
        Start onboarding
      </button>
    </form>
  );
}

export default function Home() {
  const { session, setSession, ready } = useSession();
  const router = useRouter();
  const [families, setFamilies] = useState<FamilyMeta[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<FamilyMeta[]>("/families")
      .then(setFamilies)
      .catch((e: Error) => setError(e.message));
  }, []);

  const open = (s: Session, to: string) => {
    setSession(s);
    router.push(to);
  };

  return (
    <main className="mx-auto max-w-6xl px-4 py-10">
      <section className="mb-10 max-w-3xl">
        <p className="font-semibold text-brand">family-vault · proof of value</p>
        <h1 className="mt-2 text-4xl font-bold leading-tight md:text-5xl">Know where everything is, before you need to.</h1>
        <p className="mt-4 text-xl text-muted">
          When someone in an Indian family dies or falls ill, relatives often don&apos;t know which LIC policies, FDs,
          bank accounts or shares exist, who the nominee is, or where the papers are. Money goes unclaimed.
        </p>
        <ul className="mt-5 grid gap-3 text-lg md:grid-cols-3">
          <li className="card">
            <strong>1. Map it.</strong> Record assets, nominees and where papers are kept. Only the last 4 digits of any number.
          </li>
          <li className="card">
            <strong>2. Find the gaps.</strong> Missing nominees, minors without guardians, things only one person knows.
          </li>
          <li className="card">
            <strong>3. Be ready.</strong> A step-by-step &quot;if something happens&quot; checklist for the family.
          </li>
        </ul>
        {ready && session && (
          <button className="btn-primary mt-6" onClick={() => router.push(session.principal.role === "owner" ? "/dashboard" : "/map")}>
            Continue with {session.family.display_name}
          </button>
        )}
      </section>

      <h2 className="mb-4 text-2xl font-bold">Try a sample family</h2>
      <ErrorBox message={error} />
      <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
        {families
          ?.filter((f) => f.id in DEMO_PASSPHRASES)
          .map((f) => <FamilyCard key={f.id} fam={f} onUnlocked={(s) => open(s, "/dashboard")} />)}
        <NewFamily onCreated={(s) => open(s, "/onboarding")} />
      </div>
      {families && families.some((f) => !(f.id in DEMO_PASSPHRASES)) && (
        <>
          <h2 className="mb-4 mt-10 text-2xl font-bold">Your other demo vaults</h2>
          <div className="grid gap-5 md:grid-cols-3">
            {families
              .filter((f) => !(f.id in DEMO_PASSPHRASES))
              .map((f) => <FamilyCard key={f.id} fam={f} onUnlocked={(s) => open(s, "/dashboard")} />)}
          </div>
        </>
      )}
    </main>
  );
}
