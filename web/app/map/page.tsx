"use client";

import { useCallback, useMemo, useState } from "react";

import { EstateMap, label } from "@/components/EstateMap";
import { Shell } from "@/components/Shell";
import { ErrorBox, Loading, PageTitle, SeverityBadge } from "@/components/ui";
import type { Graph } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const LEGEND = [
  ["#0f6b63", "Person"],
  ["#3b5bdb", "Asset"],
  ["#c2410c", "Loan / card"],
  ["#667085", "Institution"],
  ["#b8a98a", "Document"],
  ["#7a5af8", "Advisor"],
];
const FIELD_LABEL: Record<string, string> = {
  asset_type: "Type",
  masked_id: "Number (last 4)",
  maturity_date: "Matures on",
  expiry_date: "Expires on",
  value_band: "Approx. value",
  notes: "Notes",
  relation: "Relation",
  location: "Kept at",
  doc_type: "Document",
  kind: "Kind",
  city: "City",
  liability_type: "Type",
  subtype: "Kind",
  is_alive: "Alive",
  reachable: "Reachable",
};

function MapPage() {
  const { data, error } = useApi<Graph>("/graph");
  const [selected, setSelected] = useState<string | null>(null);
  const [showDocs, setShowDocs] = useState(false);
  const [showKnows, setShowKnows] = useState(false);
  const onSelect = useCallback((id: string | null) => setSelected(id), []);
  const node = useMemo(() => data?.nodes.find((n) => n.id === selected), [data, selected]);
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading what="Drawing the estate map" />;
  const edges = selected ? data.edges.filter((e) => e.src === selected || e.dst === selected) : [];
  const name = (id: string) => {
    const n = data.nodes.find((x) => x.id === id);
    return n ? label(n) : id;
  };

  return (
    <>
      <PageTitle title="Estate map" sub="Who owns what, where it is held, and who the nominee is. Coloured rings mark gaps — tap anything for details." />
      <div className="no-print mb-3 flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2">
          <input type="checkbox" className="size-5" checked={showDocs} onChange={(e) => setShowDocs(e.target.checked)} /> Show documents
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" className="size-5" checked={showKnows} onChange={(e) => setShowKnows(e.target.checked)} /> Show
          &quot;who knows&quot;
        </label>
        <ul className="flex flex-wrap gap-3 text-sm" aria-label="Legend">
          {LEGEND.map(([c, l]) => (
            <li key={l} className="flex items-center gap-1">
              <span className="inline-block size-3.5 rounded-sm" style={{ background: c }} />
              {l}
            </li>
          ))}
          <li className="flex items-center gap-1">
            <span className="inline-block size-3.5 rounded-full border-4 border-sev-critical" /> gap
          </li>
        </ul>
      </div>
      <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">
        <EstateMap graph={data} showDocs={showDocs} showKnows={showKnows} onSelect={onSelect} />
        <aside className="card" aria-live="polite">
          {!node && (
            <>
              <h2 className="text-lg font-bold">Tap a person, asset or institution</h2>
              <p className="mt-2 text-muted">
                {data.visible_items.length} assets and loans are visible to you. Gaps:{" "}
                {Object.values(data.gaps_by_node).flat().filter((g, i, a) => a.findIndex((x) => x.key === g.key) === i).length}.
              </p>
            </>
          )}
          {node && (
            <>
              <p className="text-sm uppercase tracking-wide text-muted">{node.cls}</p>
              <h2 className="text-xl font-bold">{label(node)}</h2>
              <dl className="mt-3 space-y-1">
                {Object.entries(node.props)
                  .filter(([k]) => !["name", "label", "household", "is_earner"].includes(k))
                  .map(([k, v]) => (
                    <div key={k} className="flex justify-between gap-3">
                      <dt className="text-muted">{FIELD_LABEL[k] ?? k}</dt>
                      <dd className="text-right font-semibold">{String(v).replaceAll("_", " ")}</dd>
                    </div>
                  ))}
              </dl>
              {node.hidden_fields && <p className="mt-2 text-sm text-muted">Hidden for your role: {node.hidden_fields.join(", ")}</p>}
              {(data.gaps_by_node[node.id] ?? []).length > 0 && (
                <ul className="mt-4 space-y-2">
                  {data.gaps_by_node[node.id].map((g) => (
                    <li key={g.key} className="flex flex-wrap items-center gap-2">
                      <SeverityBadge severity={g.severity} /> {g.title}
                    </li>
                  ))}
                </ul>
              )}
              <h3 className="mt-4 font-bold">Connections</h3>
              <ul className="mt-1 space-y-1 text-base">
                {edges.map((e) => (
                  <li key={e.id}>
                    {name(e.src)} <span className="text-muted">— {e.rel.replaceAll("_", " ")} →</span> {name(e.dst)}
                  </li>
                ))}
              </ul>
              <p className="mt-4 text-xs text-muted">
                Source: {node.provenance.source} · {node.provenance.method} · confidence {node.provenance.confidence}
              </p>
            </>
          )}
        </aside>
      </div>
    </>
  );
}

export default function Page() {
  return (
    <Shell>
      <MapPage />
    </Shell>
  );
}
