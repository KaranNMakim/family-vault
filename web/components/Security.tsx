"use client";

import { useEffect, useState } from "react";

import { secondsLeft, STEP, totpCode } from "@/lib/totp";

export function LockIcon({ className = "size-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <rect x="4" y="10" width="16" height="11" rx="2.5" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3" />
      <circle cx="12" cy="15.5" r="1.5" fill="currentColor" />
    </svg>
  );
}

export function ShieldIcon({ className = "size-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6l8-3z" />
      <path d="M8.5 12l2.5 2.5 4.5-5" />
    </svg>
  );
}

const CUES = [
  ["Encrypted vault", "Argon2id key from your passphrase; sensitive fields sealed with XChaCha20-Poly1305. The key is never stored."],
  ["2-step verification", "Passphrase plus a 6-digit code from an authenticator app (TOTP, RFC 6238)."],
  ["Lockout & auto-lock", "5 wrong attempts lock the vault for 5 minutes; sessions lock after 15 minutes idle."],
  ["Every access audited", "A tamper-evident, hash-chained log of who opened what, and when."],
];

export function SecurityPanel({ compact = false }: { compact?: boolean }) {
  return (
    <section aria-label="How your family's vault is protected" className="rounded-2xl border border-brand/30 bg-brand-soft p-5">
      <div className="flex items-center gap-2 font-bold text-brand-dark">
        <ShieldIcon className="size-6" /> How this vault is protected
      </div>
      <ul className={`mt-3 grid gap-3 ${compact ? "" : "md:grid-cols-2 lg:grid-cols-4"}`}>
        {CUES.map(([t, d]) => (
          <li key={t} className="flex gap-2">
            <LockIcon className="mt-1 size-4 shrink-0 text-brand" />
            <span>
              <strong>{t}.</strong> <span className="text-muted">{d}</span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function StepIndicator({ step }: { step: 1 | 2 }) {
  const item = (n: number, label: string) => (
    <li className={`flex items-center gap-2 ${step === n ? "font-bold text-brand" : step > n ? "text-muted" : "text-muted"}`}>
      <span
        className={`flex size-7 items-center justify-center rounded-full text-sm font-bold ${
          step > n ? "bg-brand text-white" : step === n ? "border-2 border-brand text-brand" : "border border-line"
        }`}
      >
        {step > n ? "✓" : n}
      </span>
      {label}
    </li>
  );
  return (
    <ol className="flex flex-wrap items-center gap-3 text-sm" aria-label="Unlock steps">
      {item(1, "Passphrase")}
      <li aria-hidden className="text-muted">
        →
      </li>
      {item(2, "Authenticator code")}
    </ol>
  );
}

/** Stand-in for the authenticator app on the family's phone (demo only). */
export function DemoAuthenticator({ secret, label }: { secret: string; label: string }) {
  const [code, setCode] = useState("······");
  const [left, setLeft] = useState(secondsLeft());
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      const c = await totpCode(secret);
      if (alive) {
        setCode(c);
        setLeft(secondsLeft());
      }
    };
    void tick();
    const id = setInterval(() => void tick(), 1000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [secret]);
  return (
    <div className="rounded-2xl border border-dashed border-line bg-paper p-4" aria-label="Demo authenticator app">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">Demo authenticator · stands in for the app on your phone</p>
      <div className="mt-2 flex items-center justify-between gap-3">
        <div>
          <div className="text-sm text-muted">{label}</div>
          <div className="whitespace-nowrap font-mono text-2xl font-bold tracking-[0.2em] text-ink" aria-live="polite">
            {code.slice(0, 3)} {code.slice(3)}
          </div>
        </div>
        <div className="text-center text-sm text-muted">
          <svg width="40" height="40" viewBox="0 0 40 40" aria-hidden>
            <circle cx="20" cy="20" r="16" fill="none" stroke="#e5e1d8" strokeWidth="4" />
            <circle
              cx="20"
              cy="20"
              r="16"
              fill="none"
              stroke="#0f6b63"
              strokeWidth="4"
              strokeDasharray={`${(left / STEP) * 100.5} 100.5`}
              transform="rotate(-90 20 20)"
            />
          </svg>
          {left}s
        </div>
      </div>
    </div>
  );
}

export function CodeInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <label>
      <span className="label">6-digit code from your authenticator app</span>
      <input
        className="field text-center font-mono text-2xl tracking-[0.5em]"
        inputMode="numeric"
        autoComplete="one-time-code"
        pattern="[0-9]{6}"
        maxLength={6}
        value={value}
        onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, 6))}
        placeholder="••••••"
        aria-describedby="code-help"
      />
      <span id="code-help" className="text-sm text-muted">
        Codes change every 30 seconds and can only be used once.
      </span>
    </label>
  );
}
