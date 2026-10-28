"use client";

import { useState } from "react";

import { ChecklistView } from "@/components/ChecklistView";
import { Shell } from "@/components/Shell";
import { ErrorBox, Loading, PageTitle } from "@/components/ui";
import { api, downloadBlob } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { Checklist, Item } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const SCENARIOS: [string, string][] = [
  ["death_of_earner", "If the earning member dies"],
  ["incapacity", "If they fall seriously ill"],
  ["loss_of_documents", "If papers are lost"],
];

function ChecklistPage() {
  const { session } = useSession();
  const [scenario, setScenario] = useState("death_of_earner");
  const [subject, setSubject] = useState("");
  const full = session?.principal.role === "owner" || session?.principal.role === "spouse";
  const people = useApi<Item[]>(full ? "/people" : null);
  const q = subject ? `?subject=${encodeURIComponent(subject)}` : "";
  const { data, error } = useApi<Checklist>(`/checklist/${scenario}${q}`);
  const [pdfError, setPdfError] = useState<string | null>(null);

  return (
    <>
      <PageTitle title="If something happens" sub="A step-by-step plan for the family, built from what is recorded in the vault." />
      <div className="no-print mb-6 flex flex-wrap items-end gap-3">
        <div role="tablist" aria-label="Scenario" className="flex flex-wrap gap-2">
          {SCENARIOS.map(([id, l]) => (
            <button key={id} role="tab" aria-selected={scenario === id} className={scenario === id ? "btn-primary" : "btn-secondary"} onClick={() => setScenario(id)}>
              {l}
            </button>
          ))}
        </div>
        {full && people.data && (
          <label className="min-w-56">
            <span className="label">For whom</span>
            <select className="field" value={subject} onChange={(e) => setSubject(e.target.value)}>
              <option value="">Main earner (default)</option>
              {people.data
                .filter((p) => p.props.is_alive !== false && p.props.household !== false)
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {String(p.props.name)}
                  </option>
                ))}
            </select>
          </label>
        )}
        <button className="btn-secondary" onClick={() => window.print()}>
          Print
        </button>
        <button
          className="btn-secondary"
          onClick={async () => {
            setPdfError(null);
            try {
              const blob = await api<Blob>(`/checklist/${scenario}/pdf${q}`, { token: session?.token, raw: true });
              downloadBlob(blob, `checklist-${scenario}.pdf`);
            } catch (e) {
              setPdfError(e instanceof Error ? e.message : String(e));
            }
          }}
        >
          Download PDF
        </button>
      </div>
      <ErrorBox message={error ?? pdfError} />
      {!data && !error && <Loading what="Preparing the checklist" />}
      {data && (
        <>
          <h2 className="mb-3 text-2xl font-bold">
            {data.scenario_label}: {data.subject_name}
          </h2>
          <ChecklistView cl={data} />
        </>
      )}
    </>
  );
}

export default function Page() {
  return (
    <Shell>
      <ChecklistPage />
    </Shell>
  );
}
