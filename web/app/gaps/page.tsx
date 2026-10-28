"use client";

import { useState } from "react";

import { FixGap } from "@/components/FixGap";
import { Shell } from "@/components/Shell";
import { ErrorBox, Loading, PageTitle, SeverityBadge } from "@/components/ui";
import { useSession } from "@/lib/session";
import type { Gap, Item, Readiness, Severity } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const ORDER: Severity[] = ["critical", "high", "medium", "low", "info"];

function Gaps() {
  const { session, bump } = useSession();
  const full = session?.principal.role === "owner" || session?.principal.role === "spouse";
  const gaps = useApi<Gap[]>("/gaps");
  const people = useApi<Item[]>("/people");
  const r = useApi<Readiness>(full ? "/readiness" : null);
  const [flash, setFlash] = useState<string | null>(null);
  if (gaps.error) return <ErrorBox message={gaps.error} />;
  if (!gaps.data || !people.data) return <Loading />;
  const gain = Object.fromEntries((r.data?.impacts ?? []).map((i) => [i.key, i.points_if_fixed]));

  return (
    <>
      <PageTitle
        title="Gaps we found"
        sub={
          <>
            Each gap is a rule we check, with a plain-language fix.
            {r.data && (
              <>
                {" "}
                Current readiness: <strong>{r.data.score}/100</strong>.
              </>
            )}
          </>
        }
      />
      {flash && (
        <p role="status" className="mb-4 rounded-xl bg-brand-soft px-4 py-3 font-semibold">
          {flash}
        </p>
      )}
      {gaps.data.length === 0 && <p className="card">No gaps found. Your family is well prepared.</p>}
      <ol className="space-y-4">
        {[...gaps.data]
          .sort((a, b) => ORDER.indexOf(a.severity) - ORDER.indexOf(b.severity))
          .map((g) => (
            <li key={g.key} className="card" id={g.key}>
              <div className="flex flex-wrap items-center gap-2">
                <SeverityBadge severity={g.severity} />
                <h2 className="text-lg font-bold">{g.title}</h2>
                {gain[g.key] > 0 && <span className="chip ml-auto bg-brand-soft text-brand">Fixing this: +{gain[g.key]} points</span>}
              </div>
              <p className="mt-2 text-lg">{g.message}</p>
              <p className="mt-2 text-muted">
                <strong className="text-ink">What to do: </strong>
                {g.fix}
              </p>
              <div className="mt-3">
                <FixGap
                  gap={g}
                  people={people.data ?? []}
                  onFixed={() => {
                    setFlash(`Saved. "${g.title}" is fixed.`);
                    bump();
                  }}
                />
              </div>
              <p className="mt-2 text-xs text-muted">Rule {g.rule} · deterministic check · ref {g.key}</p>
            </li>
          ))}
      </ol>
    </>
  );
}

export default function Page() {
  return (
    <Shell>
      <Gaps />
    </Shell>
  );
}
