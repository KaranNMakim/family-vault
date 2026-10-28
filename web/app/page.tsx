"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { LockIcon, SecurityPanel, StepIndicator } from "@/components/Security";
import { type Challenge, DEMO, rememberSecret, VerifyStep } from "@/components/Unlock";
import { ErrorBox } from "@/components/ui";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { FamilyMeta, Session } from "@/lib/types";

function FamilyCard({ fam, onUnlocked }: { fam: FamilyMeta; onUnlocked: (s: Session) => void }) {
  const [pass, setPass] = useState(DEMO[fam.id]?.passphrase ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [challenge, setChallenge] = useState<Challenge | null>(null);

  return (
    <div className="card flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-xl font-bold">{fam.display_name}</h3>
        <LockIcon className="size-6 shrink-0 text-brand" />
      </div>
      {!challenge && fam.story && <p className="text-base text-muted">{fam.story}</p>}
      {challenge ? (
        <VerifyStep challenge={challenge} label={fam.display_name} onDone={onUnlocked} onBack={() => setChallenge(null)} />
      ) : (
        <form
          className="mt-auto flex flex-col gap-3"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError(null);
            try {
              const c = await api<Challenge>("/session/unlock", { body: { family_id: fam.id, passphrase: pass } });
              if (c.enroll) rememberSecret(fam.id, c.enroll.secret);
              setChallenge(c);
            } catch (err) {
              setError(err instanceof Error ? err.message : String(err));
            } finally {
              setBusy(false);
            }
          }}
        >
          <StepIndicator step={1} />
          <label>
            <span className="label">Vault passphrase</span>
            <input className="field" type="password" value={pass} onChange={(e) => setPass(e.target.value)} autoComplete="current-password" />
            {DEMO[fam.id] && <span className="text-sm text-muted">Demo passphrase pre-filled.</span>}
          </label>
          <ErrorBox message={error} />
          <button className="btn-primary" disabled={busy || pass.length < 8}>
            {busy ? "Checking…" : "Continue"}
          </button>
        </form>
      )}
    </div>
  );
}

function NewFamily({ onCreated }: { onCreated: (s: Session) => void }) {
  const [name, setName] = useState("");
  const [pass, setPass] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [challenge, setChallenge] = useState<Challenge | null>(null);

  if (challenge?.enroll) {
    const groups = challenge.enroll.secret.match(/.{1,4}/g)?.join(" ");
    return (
      <div className="card flex flex-col gap-3">
        <h3 className="text-xl font-bold">Set up 2-step verification</h3>
        <p className="text-base">
          Add this key to an authenticator app (Google Authenticator, Microsoft Authenticator, Authy…) — choose <em>Enter a setup key</em>, time-based.
        </p>
        <p className="rounded-xl bg-paper px-3 py-2 text-center font-mono text-lg tracking-wider" aria-label="Setup key">
          {groups}
        </p>
        <VerifyStep challenge={challenge} label={name} onDone={onCreated} onBack={() => setChallenge(null)} />
      </div>
    );
  }
  return (
    <form
      className="card flex flex-col gap-3"
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        try {
          const c = await api<Challenge>("/vaults", { body: { display_name: name, passphrase: pass } });
          if (c.enroll) rememberSecret(c.family_id, c.enroll.secret);
          setChallenge(c);
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
        Create vault and set up 2-step verification
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
      <section className="mb-8 max-w-3xl">
        <p className="font-semibold text-brand">family-vault · proof of value</p>
        <h1 className="mt-2 text-4xl font-bold leading-tight md:text-5xl">Know where everything is, before you need to.</h1>
        <p className="mt-4 text-xl text-muted">
          When someone in an Indian family dies or falls ill, relatives often don&apos;t know which LIC policies, FDs, bank accounts or shares
          exist, who the nominee is, or where the papers are. Money goes unclaimed.
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

      <div className="mb-8">
        <SecurityPanel />
      </div>

      <h2 className="mb-4 text-2xl font-bold">Unlock a sample family</h2>
      <ErrorBox message={error} />
      <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
        {families
          ?.filter((f) => f.id in DEMO)
          .map((f) => <FamilyCard key={f.id} fam={f} onUnlocked={(s) => open(s, "/dashboard")} />)}
        <NewFamily onCreated={(s) => open(s, "/onboarding")} />
      </div>
      {families && families.some((f) => !(f.id in DEMO)) && (
        <>
          <h2 className="mb-4 mt-10 text-2xl font-bold">Your other demo vaults</h2>
          <div className="grid gap-5 md:grid-cols-3">
            {families
              .filter((f) => !(f.id in DEMO))
              .map((f) => <FamilyCard key={f.id} fam={f} onUnlocked={(s) => open(s, "/dashboard")} />)}
          </div>
        </>
      )}
    </main>
  );
}
