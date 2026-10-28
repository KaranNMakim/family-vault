"use client";

import type { Core, ElementDefinition } from "cytoscape";
import { useEffect, useRef } from "react";

import type { Graph, Severity } from "@/lib/types";

const SEV_RANK: Severity[] = ["critical", "high", "medium", "low", "info"];
const SEV_COLOR: Record<Severity, string> = {
  critical: "#b42318",
  high: "#c4320a",
  medium: "#d89b00",
  low: "#98a2b3",
  info: "#98a2b3",
};
const REL_LABEL: Record<string, string> = {
  owns: "owns",
  nominee_of: "nominee",
  held_at: "held at",
  documented_by: "papers",
  guardian_of: "guardian of",
  advised_by: "advisor",
  knows_about: "knows",
};

export function label(n: Graph["nodes"][number]): string {
  const p = n.props as Record<string, string | undefined>;
  return p.name ?? p.label ?? n.id;
}

export function toElements(g: Graph, showDocs: boolean, showKnows: boolean): ElementDefinition[] {
  const nodes = g.nodes.filter((n) => showDocs || n.cls !== "Document");
  const ids = new Set(nodes.map((n) => n.id));
  const els: ElementDefinition[] = nodes.map((n) => {
    const gaps = g.gaps_by_node[n.id] ?? [];
    const worst = gaps.map((x) => x.severity).sort((a, b) => SEV_RANK.indexOf(a) - SEV_RANK.indexOf(b))[0];
    const p = n.props as Record<string, unknown>;
    return {
      data: {
        id: n.id,
        label: label(n),
        cls: n.cls,
        gap: worst ?? "",
        gapColor: worst ? SEV_COLOR[worst] : "#ffffff",
        dead: p.is_alive === false ? "yes" : "",
      },
    };
  });
  for (const e of g.edges) {
    if (!ids.has(e.src) || !ids.has(e.dst)) continue;
    if (e.rel === "knows_about" && !showKnows) continue;
    els.push({ data: { id: e.id, source: e.src, target: e.dst, rel: e.rel, label: REL_LABEL[e.rel] ?? e.rel } });
  }
  return els;
}

export function EstateMap({
  graph,
  showDocs,
  showKnows,
  onSelect,
}: {
  graph: Graph;
  showDocs: boolean;
  showKnows: boolean;
  onSelect: (id: string | null) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);

  useEffect(() => {
    let cancelled = false;
    void import("cytoscape").then(({ default: cytoscape }) => {
      if (cancelled || !ref.current) return;
      cyRef.current?.destroy();
      const cy = cytoscape({
        container: ref.current,
        elements: toElements(graph, showDocs, showKnows),
        wheelSensitivity: 0.3,
        style: [
          {
            selector: "node",
            style: {
              label: "data(label)",
              "font-size": 13,
              "text-wrap": "wrap",
              "text-max-width": "120px",
              "text-valign": "bottom",
              "text-margin-y": 6,
              color: "#1c2530",
              width: 38,
              height: 38,
              "border-width": 3,
              "border-color": "#ffffff",
            },
          },
          { selector: 'node[cls = "Person"]', style: { "background-color": "#0f6b63", shape: "ellipse" } },
          { selector: 'node[dead = "yes"]', style: { "background-color": "#98a2b3", "border-style": "dashed" } },
          { selector: 'node[cls = "Asset"]', style: { "background-color": "#3b5bdb", shape: "round-rectangle", width: 46 } },
          { selector: 'node[cls = "Liability"]', style: { "background-color": "#c2410c", shape: "round-rectangle", width: 46 } },
          { selector: 'node[cls = "Institution"]', style: { "background-color": "#667085", shape: "hexagon" } },
          { selector: 'node[cls = "Document"]', style: { "background-color": "#b8a98a", shape: "tag", width: 26, height: 26, "font-size": 11 } },
          { selector: 'node[cls = "Advisor"]', style: { "background-color": "#7a5af8", shape: "diamond" } },
          { selector: 'node[gap != ""]', style: { "border-width": 6, "border-color": "data(gapColor)" } },
          { selector: "node:selected", style: { "overlay-color": "#0f6b63", "overlay-opacity": 0.15 } },
          {
            selector: "edge",
            style: {
              width: 2,
              "line-color": "#c9c2b3",
              "target-arrow-color": "#c9c2b3",
              "target-arrow-shape": "triangle",
              "curve-style": "bezier",
              label: "data(label)",
              "font-size": 10,
              color: "#4b5563",
              "text-background-color": "#faf8f4",
              "text-background-opacity": 1,
              "text-background-padding": "2px",
            },
          },
          { selector: 'edge[rel = "nominee_of"]', style: { "line-color": "#0f6b63", "target-arrow-color": "#0f6b63", width: 3 } },
          { selector: 'edge[rel = "knows_about"]', style: { "line-style": "dotted" } },
          { selector: 'edge[rel = "guardian_of"]', style: { "line-color": "#7a5af8", "target-arrow-color": "#7a5af8" } },
        ],
        layout: { name: "cose", animate: false, nodeRepulsion: () => 9000, idealEdgeLength: () => 90, randomize: false, padding: 20 },
      });
      cy.on("tap", "node", (e) => onSelect(e.target.id()));
      cy.on("tap", (e) => {
        if (e.target === cy) onSelect(null);
      });
      cyRef.current = cy;
    });
    return () => {
      cancelled = true;
      cyRef.current?.destroy();
      cyRef.current = null;
    };
  }, [graph, showDocs, showKnows, onSelect]);

  return <div ref={ref} className="h-[60vh] min-h-96 w-full rounded-2xl border border-line bg-white" aria-label="Estate map (interactive graph)" role="img" />;
}
