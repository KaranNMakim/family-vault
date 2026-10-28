"use client";

import type { Checklist } from "@/lib/types";

export function ChecklistView({ cl }: { cl: Checklist }) {
  return (
    <div>
      <p className="mb-4 rounded-xl bg-warn-soft px-4 py-3 text-base font-semibold">{cl.disclaimer}</p>
      {cl.blocked_count > 0 && (
        <p className="mb-4 text-lg">
          <strong className="text-sev-critical">{cl.blocked_count} step(s) would be blocked today</strong> because of gaps. Fixing those
          gaps now makes this much easier for your family.
        </p>
      )}
      <ol className="space-y-4">
        {cl.steps.map((s) => (
          <li key={s.order} className={`card ${s.blocked ? "border-l-8 border-l-sev-critical" : ""}`}>
            <div className="flex gap-3">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-brand text-lg font-bold text-white" aria-hidden>
                {s.order}
              </span>
              <div className="min-w-0">
                <p className="text-lg font-semibold">
                  {s.text}
                  {s.blocked && <span className="chip ml-2 bg-sev-critical text-white">Blocked by a gap</span>}
                </p>
                {s.institution && <p className="text-muted">At: {s.institution}</p>}
                <p className="mt-2">
                  <strong>Who should do this: </strong>
                  {s.actors.join(", ")}
                </p>
                {s.required_documents.length > 0 && (
                  <div className="mt-2">
                    <strong>Take these documents:</strong>
                    <ul className="ml-6 list-disc">
                      {s.required_documents.map((d) => (
                        <li key={d}>{d}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {s.notes.map((n) => (
                  <p key={n} className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-base text-sev-critical">
                    {n}
                  </p>
                ))}
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
