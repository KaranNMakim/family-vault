"use client";

import type { Severity } from "@/lib/types";

const SEV_STYLE: Record<Severity, string> = {
  critical: "bg-sev-critical text-white",
  high: "bg-sev-high text-white",
  medium: "bg-warn-soft text-sev-medium border border-sev-medium/40",
  low: "bg-slate-100 text-sev-low",
  info: "bg-slate-100 text-sev-info",
};
const SEV_LABEL: Record<Severity, string> = {
  critical: "Urgent",
  high: "Important",
  medium: "Worth fixing",
  low: "Minor",
  info: "For information",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <span className={`chip ${SEV_STYLE[severity]}`}>{SEV_LABEL[severity]}</span>;
}

export function DemoBanner() {
  return (
    <div role="note" className="bg-warn-soft px-4 py-2 text-center text-sm font-semibold text-ink">
      Demo only — all families here are fictional. Do not enter real account numbers, ID numbers or passwords.
    </div>
  );
}

export function ErrorBox({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div role="alert" className="rounded-xl border border-sev-critical/40 bg-red-50 px-4 py-3 text-sev-critical">
      {message}
    </div>
  );
}

export function Loading({ what = "Loading" }: { what?: string }) {
  return <p className="text-muted">{what}…</p>;
}

export function PageTitle({ title, sub }: { title: string; sub?: React.ReactNode }) {
  return (
    <div className="mb-6">
      <h1 className="text-3xl font-bold tracking-tight">{title}</h1>
      {sub && <p className="mt-1 max-w-3xl text-lg text-muted">{sub}</p>}
    </div>
  );
}

export function ScoreRing({ score, band }: { score: number; band: string }) {
  const r = 52;
  const c = 2 * Math.PI * r;
  const color = score >= 85 ? "#0f6b63" : score >= 65 ? "#2f7d4f" : score >= 40 ? "#946200" : "#b42318";
  return (
    <div className="flex items-center gap-5">
      <svg width="132" height="132" viewBox="0 0 132 132" role="img" aria-label={`Readiness ${score} out of 100`}>
        <circle cx="66" cy="66" r={r} fill="none" stroke="#e5e1d8" strokeWidth="14" />
        <circle
          cx="66"
          cy="66"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="14"
          strokeLinecap="round"
          strokeDasharray={`${(score / 100) * c} ${c}`}
          transform="rotate(-90 66 66)"
        />
        <text x="66" y="74" textAnchor="middle" fontSize="34" fontWeight="700" fill="#1c2530">
          {score}
        </text>
      </svg>
      <div>
        <div className="text-sm uppercase tracking-wide text-muted">Family readiness</div>
        <div className="text-2xl font-bold">{band}</div>
      </div>
    </div>
  );
}

export function PersonSelect({
  people,
  value,
  onChange,
  label,
  exclude = [],
}: {
  people: { id: string; name: string }[];
  value: string;
  onChange: (v: string) => void;
  label: string;
  exclude?: string[];
}) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      <select className="field" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Choose…</option>
        {people
          .filter((p) => !exclude.includes(p.id))
          .map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
      </select>
    </label>
  );
}

export function GuidanceNote({ text }: { text: string }) {
  return <p className="rounded-xl bg-brand-soft px-4 py-3 text-base">{text}</p>;
}
