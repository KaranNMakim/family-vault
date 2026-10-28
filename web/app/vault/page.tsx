"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Shell } from "@/components/Shell";
import { ErrorBox, GuidanceNote, Loading, PageTitle } from "@/components/ui";
import { api, downloadBlob } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { Session } from "@/lib/types";
import { useApi } from "@/lib/useApi";

interface AuditOut {
  chain_valid: boolean;
  first_bad_seq: number | null;
  entries: { seq: number; ts: string; actor: string; role: string; action: string; target: string }[];
}

function toBase64(buf: ArrayBuffer): string {
  let s = "";
  const bytes = new Uint8Array(buf);
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
  return btoa(s);
}

function VaultPage() {
  const { session, setSession } = useSession();
  const router = useRouter();
  const audit = useApi<AuditOut>("/audit");
  const [exportPass, setExportPass] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [importPass, setImportPass] = useState("");
  const [newPass, setNewPass] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  return (
    <>
      <PageTitle title="Vault & audit" sub="Encrypted backup, restore, and a tamper-evident record of every access and change." />
      <ErrorBox message={error} />
      {info && (
        <p role="status" className="mb-4 rounded-xl bg-brand-soft px-4 py-3 font-semibold">
          {info}
        </p>
      )}
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card grid gap-3">
          <h2 className="text-xl font-bold">Encrypted export</h2>
          <GuidanceNote text="The export is encrypted with the passphrase you choose here (Argon2id + XChaCha20-Poly1305). Without it, the file is useless — to anyone, including you." />
          <label>
            <span className="label">Export passphrase (8+ characters)</span>
            <input className="field" type="password" value={exportPass} onChange={(e) => setExportPass(e.target.value)} autoComplete="new-password" />
          </label>
          <button
            className="btn-primary"
            disabled={exportPass.length < 8}
            onClick={async () => {
              setError(null);
              try {
                const blob = await api<Blob>("/export", { token: session?.token, body: { passphrase: exportPass }, raw: true });
                downloadBlob(blob, `${session?.family.id ?? "family"}.fvault`);
                setInfo("Encrypted export downloaded.");
              } catch (e) {
                setError(e instanceof Error ? e.message : String(e));
              }
            }}
          >
            Download encrypted export
          </button>
        </section>

        <section className="card grid gap-3">
          <h2 className="text-xl font-bold">Import into a new vault</h2>
          <label>
            <span className="label">Export file (.fvault)</span>
            <input className="field" type="file" accept=".fvault" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
          <label>
            <span className="label">Passphrase used for the export</span>
            <input className="field" type="password" value={importPass} onChange={(e) => setImportPass(e.target.value)} autoComplete="off" />
          </label>
          <label>
            <span className="label">Passphrase for the new vault</span>
            <input className="field" type="password" value={newPass} onChange={(e) => setNewPass(e.target.value)} autoComplete="new-password" />
          </label>
          <button
            className="btn-secondary"
            disabled={!file || !importPass || newPass.length < 8}
            onClick={async () => {
              setError(null);
              try {
                const blob_b64 = toBase64(await file!.arrayBuffer());
                const s = await api<Session>("/import", {
                  body: { blob_b64, export_passphrase: importPass, new_vault_passphrase: newPass, display_name: `${session?.family.display_name} (restored)` },
                });
                setSession(s);
                router.push("/dashboard");
              } catch (e) {
                setError(e instanceof Error ? e.message : String(e));
              }
            }}
          >
            Import and open
          </button>
        </section>
      </div>

      <section className="card mt-6">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-xl font-bold">Audit log</h2>
          {audit.data && (
            <span className={`chip ${audit.data.chain_valid ? "bg-brand-soft text-brand" : "bg-sev-critical text-white"}`}>
              {audit.data.chain_valid ? "Hash chain verified — no tampering" : `Tampering detected at entry ${audit.data.first_bad_seq}`}
            </span>
          )}
          <button className="btn-secondary ml-auto min-h-10 py-1" onClick={() => void audit.reload()}>
            Refresh
          </button>
        </div>
        {!audit.data && <Loading />}
        {audit.data && (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-base">
              <thead>
                <tr className="border-b border-line">
                  <th className="py-2 pr-3">#</th>
                  <th className="py-2 pr-3">When</th>
                  <th className="py-2 pr-3">Who</th>
                  <th className="py-2 pr-3">Role</th>
                  <th className="py-2 pr-3">What</th>
                  <th className="py-2">Target</th>
                </tr>
              </thead>
              <tbody>
                {audit.data.entries.slice(0, 100).map((e) => (
                  <tr key={e.seq} className="border-b border-line/60">
                    <td className="py-1.5 pr-3 text-muted">{e.seq}</td>
                    <td className="py-1.5 pr-3 whitespace-nowrap">{new Date(e.ts).toLocaleString("en-IN")}</td>
                    <td className="py-1.5 pr-3">{e.actor}</td>
                    <td className="py-1.5 pr-3">{e.role}</td>
                    <td className="py-1.5 pr-3 font-semibold">{e.action}</td>
                    <td className="py-1.5">{e.target}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

export default function Page() {
  return (
    <Shell>
      <VaultPage />
    </Shell>
  );
}
