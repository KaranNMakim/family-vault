"use client";

import Link from "next/link";

import { Shell } from "@/components/Shell";
import { ErrorBox, Loading, PageTitle, ScoreRing, SeverityBadge } from "@/components/ui";
import { useSession } from "@/lib/session";
import type { Gap, Readiness } from "@/lib/types";
import { useApi } from "@/lib/useApi";

function Dashboard() {
  const { session } = useSession();
  const r = useApi<Readiness>("/readiness");
  const g = useApi<Gap[]>("/gaps");
  if (r.error) return <ErrorBox message={r.error} />;
  if (!r.data || !g.data) return <Loading />;
  const byKey = Object.fromEntries(g.data.map((x) => [x.key, x]));
  const top = r.data.impacts.filter((i) => i.points_if_fixed > 0).slice(0, 4);
  return (
    <>
      <PageTitle title={session?.family.display_name ?? "Your family"} sub={session?.family.story} />
      <div className="grid gap-6 lg:grid-cols-[1fr_1.4fr]">
        <section className="card" aria-labelledby="score-h">
          <h2 id="score-h" className="sr-only">
            Readiness score
          </h2>
          <ScoreRing score={r.data.score} band={r.data.band} />
          <ul className="mt-5 space-y-3">
            {r.data.categories
              .filter((c) => c.max_points > 0)
              .map((c) => (
                <li key={c.category}>
                  <div className="flex justify-between text-base">
                    <span>{c.label}</span>
                    <span className="font-semibold">
                      {c.earned}/{c.max_points}
                    </span>
                  </div>
                  <div className="mt-1 h-2.5 rounded-full bg-line" aria-hidden>
                    <div className="h-2.5 rounded-full bg-brand" style={{ width: `${(100 * c.earned) / c.max_points}%` }} />
                  </div>
                </li>
              ))}
          </ul>
          <p className="mt-4 text-sm text-muted">{r.data.explanation}</p>
        </section>

        <section className="card" aria-labelledby="fix-h">
          <h2 id="fix-h" className="text-xl font-bold">
            Fix these first
          </h2>
          <p className="text-muted">The biggest improvements to your family&apos;s readiness.</p>
          <ul className="mt-4 space-y-4">
            {top.map((i) => {
              const gap = byKey[i.key];
              return (
                <li key={i.key} className="rounded-xl border border-line p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <SeverityBadge severity={gap.severity} />
                    <strong>{gap.title}</strong>
                    <span className="chip ml-auto bg-brand-soft text-brand">+{i.points_if_fixed} points</span>
                  </div>
                  <p className="mt-2">{gap.message}</p>
                </li>
              );
            })}
            {top.length === 0 && <li>No gaps that affect the score. Well done!</li>}
          </ul>
          <div className="mt-5 flex flex-wrap gap-3">
            <Link className="btn-primary" href="/gaps">
              See all {g.data.length} gaps
            </Link>
            <Link className="btn-secondary" href="/checklist">
              If something happens…
            </Link>
            <Link className="btn-secondary" href="/map">
              Estate map
            </Link>
          </div>
        </section>
      </div>
    </>
  );
}

export default function Page() {
  return (
    <Shell>
      <Dashboard />
    </Shell>
  );
}
