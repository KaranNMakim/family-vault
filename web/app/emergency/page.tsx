"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Shell } from "@/components/Shell";
import { ErrorBox, GuidanceNote, Loading, PageTitle, PersonSelect } from "@/components/ui";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { AccessRequest, Persona, Session } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const EVENT_LABEL: Record<string, string> = {
  requested: "Access requested",
  owner_notified: "Owner notified",
  cancelled: "Cancelled by owner",
  activated: "Waiting period over — read-only access opened",
  expired: "Access expired",
};

function fmt(ts: string) {
  return new Date(ts).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

function Timeline({ r, now }: { r: AccessRequest; now: string | null }) {
  const start = new Date(r.created_at).getTime();
  const end = new Date(r.available_at).getTime();
  const t = now ? new Date(now).getTime() : start;
  const pct = r.status === "pending" ? Math.min(100, Math.max(0, ((t - start) / Math.max(1, end - start)) * 100)) : 100;
  const hoursLeft = Math.max(0, Math.ceil((end - t) / 3_600_000));
  return (
    <div>
      <ol className="relative ml-3 border-l-4 border-line pl-6">
        {r.timeline.map((e, i) => (
          <li key={i} className="mb-4">
            <span className="absolute -left-[11px] mt-1.5 size-4 rounded-full bg-brand" aria-hidden />
            <p className="font-semibold">{EVENT_LABEL[e.event] ?? e.event}</p>
            <p className="text-sm text-muted">{fmt(e.ts)}</p>
          </li>
        ))}
        {r.status === "pending" && (
          <li className="mb-2">
            <span className="absolute -left-[11px] mt-1.5 size-4 rounded-full border-4 border-brand bg-white" aria-hidden />
            <p className="font-semibold">Waiting period: {hoursLeft} hour(s) left</p>
            <p className="text-sm text-muted">Opens {fmt(r.available_at)} unless the owner cancels.</p>
            <div className="mt-2 h-3 w-full max-w-md rounded-full bg-line" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
              <div className="h-3 rounded-full bg-brand" style={{ width: `${pct}%` }} />
            </div>
          </li>
        )}
      </ol>
    </div>
  );
}

const STATUS_STYLE: Record<string, string> = {
  pending: "bg-warn-soft text-sev-medium",
  active: "bg-brand text-white",
  cancelled: "bg-slate-100 text-muted",
  expired: "bg-slate-100 text-muted",
};

function EmergencyPage() {
  const { session, switchTo, bump } = useSession();
  const router = useRouter();
  const isOwner = session?.principal.role === "owner";
  const reqs = useApi<AccessRequest[]>("/access-requests");
  const clock = useApi<{ now: string }>("/demo/clock");
  const personas = useApi<Persona[]>(isOwner ? "/session/personas" : null);
  const notes = useApi<{ id: string; text: string; ts: string }[]>("/notifications");
  const [requester, setRequester] = useState("");
  const [wait, setWait] = useState(72);
  const [reason, setReason] = useState("Medical emergency");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const token = session?.token;

  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    setError(null);
    setInfo(null);
    try {
      await fn();
      if (ok) setInfo(ok);
      bump();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const createRequest = () =>
    run(async () => {
      if (isOwner) {
        // Demo: act as the nominee behind the scenes to file their request.
        const s = await api<Session>("/session/act-as", { token, body: { role: "nominee", person_id: requester } });
        await api("/access-requests", { token: s.token, body: { reason, wait_hours: wait } });
      } else {
        await api("/access-requests", { token, body: { reason, wait_hours: wait } });
      }
    }, "Request sent. The owner has been notified and the waiting period has started.");

  if (!reqs.data) return reqs.error ? <ErrorBox message={reqs.error} /> : <Loading />;
  const nominees = (personas.data ?? []).filter((p) => p.role === "nominee").map((p) => ({ id: p.person_id ?? "", name: p.label }));
  const open = reqs.data.some((r) => r.status === "pending" || r.status === "active");

  return (
    <>
      <PageTitle
        title="Emergency access (simulation)"
        sub="A trusted nominee can ask for read-only access. The owner is told immediately and has a waiting period to cancel. Only after the delay does a limited, read-only view open — and everything is logged."
      />
      <GuidanceNote text="This is a simulation with a demo clock. In a real product the waiting period, identity checks and legal terms need careful review." />
      <ErrorBox message={error} />
      {info && (
        <p role="status" className="mt-3 rounded-xl bg-brand-soft px-4 py-3 font-semibold">
          {info}
        </p>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <section className="card">
          <h2 className="text-xl font-bold">1. Request access {isOwner && "(as a nominee)"}</h2>
          <div className="mt-3 grid gap-3">
            {isOwner && <PersonSelect label="Who is asking?" people={nominees} value={requester} onChange={setRequester} />}
            <label>
              <span className="label">Reason</span>
              <input className="field" value={reason} onChange={(e) => setReason(e.target.value)} />
            </label>
            <label>
              <span className="label">Waiting period</span>
              <select className="field" value={wait} onChange={(e) => setWait(Number(e.target.value))}>
                {[24, 48, 72, 168].map((h) => (
                  <option key={h} value={h}>
                    {h} hours ({h / 24} day{h > 24 ? "s" : ""})
                  </option>
                ))}
              </select>
            </label>
            <button className="btn-primary" disabled={(isOwner && !requester) || (!isOwner && open)} onClick={() => void createRequest()}>
              Send request
            </button>
          </div>
        </section>

        <section className="card">
          <h2 className="text-xl font-bold">2. Demo clock</h2>
          <p className="mt-1 text-muted">Now (simulated): {clock.data ? fmt(clock.data.now) : "…"}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {[24, 72].map((h) => (
              <button key={h} className="btn-secondary" onClick={() => void run(() => api("/demo/clock/advance", { token, body: { hours: h } }), `Clock moved forward ${h} hours.`)}>
                Fast-forward {h}h
              </button>
            ))}
          </div>
          {isOwner && notes.data && notes.data.length > 0 && (
            <>
              <h3 className="mt-5 font-bold">Owner&apos;s notifications</h3>
              <ul className="mt-2 space-y-2">
                {notes.data.slice(0, 4).map((n) => (
                  <li key={n.id} className="rounded-lg bg-warn-soft px-3 py-2">
                    {n.text} <span className="block text-sm text-muted">{fmt(n.ts)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      </div>

      <h2 className="mb-3 mt-8 text-2xl font-bold">3. Requests</h2>
      {reqs.data.length === 0 && <p className="card">No requests yet.</p>}
      <ul className="space-y-4">
        {[...reqs.data].reverse().map((r) => (
          <li key={r.id} className="card">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <strong className="text-lg">{r.requester_name}</strong>
              <span className={`chip ${STATUS_STYLE[r.status]}`}>{r.status}</span>
              <span className="text-muted">“{r.reason}”</span>
            </div>
            <Timeline r={r} now={clock.data?.now ?? null} />
            <div className="mt-2 flex flex-wrap gap-2">
              {isOwner && r.status === "pending" && (
                <button className="btn-danger" onClick={() => void run(() => api(`/access-requests/${r.id}/cancel`, { token, body: {} }), "Request cancelled. The nominee was told.")}>
                  Cancel this request (owner)
                </button>
              )}
              {r.status === "pending" && (
                <button className="btn-secondary" onClick={() => void run(() => api(`/access-requests/${r.id}/approve-after-delay`, { token, body: {} }), "Access is now open.")}>
                  Try to open access now
                </button>
              )}
              {r.status === "active" && isOwner && (
                <button
                  className="btn-primary"
                  onClick={() =>
                    void switchTo({ role: "emergency", person_id: r.requester_id, access_request_id: r.id, label: r.requester_name }).then(() =>
                      router.push("/nominee"),
                    )
                  }
                >
                  See what {r.requester_name} sees
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}

export default function Page() {
  return (
    <Shell>
      <EmergencyPage />
    </Shell>
  );
}
