"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import type { Session } from "@/lib/types";

import { CodeInput, DemoAuthenticator, LockIcon, StepIndicator } from "./Security";
import { ErrorBox } from "./ui";

/** Synthetic demo vaults only. These passphrases and authenticator secrets protect fictional data and are published on purpose. */
export const DEMO: Record<string, { passphrase: string; totp: string }> = {
  family_a: { passphrase: "mehta-demo-vault", totp: "RGCOIPBHJMRGSNVZUIIEJCML47XZTUGS" },
  family_b: { passphrase: "agarwal-demo-vault", totp: "G4P2PJEUAT5GSSD37PE7ES23WHIJ3R7N" },
  family_c: { passphrase: "nair-demo-vault", totp: "Z5B4KSEKUBT72457CLE6YFLUHCTXMMGR" },
};

export interface Challenge {
  challenge_id: string;
  family_id: string;
  expires_in_seconds: number;
  enroll?: { secret: string; otpauth_uri: string };
}

/** Secrets of vaults created in this browser, so the demo authenticator can show their codes (like a phone app would). */
export function rememberSecret(fid: string, secret: string) {
  try {
    localStorage.setItem(`fv.totp.${fid}`, secret);
  } catch {
    /* storage unavailable */
  }
}
export function knownSecret(fid: string): string | null {
  if (DEMO[fid]) return DEMO[fid].totp;
  try {
    return localStorage.getItem(`fv.totp.${fid}`);
  } catch {
    return null;
  }
}

export function VerifyStep({ challenge, label, onDone, onBack }: { challenge: Challenge; label: string; onDone: (s: Session) => void; onBack: () => void }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const secret = challenge.enroll?.secret ?? knownSecret(challenge.family_id);
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        try {
          onDone(await api<Session>("/session/verify", { body: { challenge_id: challenge.challenge_id, code } }));
        } catch (err) {
          setError(err instanceof Error ? err.message : String(err));
          setCode("");
        } finally {
          setBusy(false);
        }
      }}
    >
      <StepIndicator step={2} />
      <p className="text-base">
        <strong>Passphrase accepted.</strong> Now enter the code from your authenticator app to finish unlocking.
      </p>
      {secret && <DemoAuthenticator secret={secret} label={label} />}
      <CodeInput value={code} onChange={setCode} />
      <ErrorBox message={error} />
      <div className="flex flex-wrap gap-2">
        <button className="btn-primary" disabled={busy || code.length !== 6}>
          <LockIcon className="size-4" /> {busy ? "Verifying…" : "Verify and unlock"}
        </button>
        <button type="button" className="btn-secondary" onClick={onBack}>
          Back
        </button>
      </div>
    </form>
  );
}

