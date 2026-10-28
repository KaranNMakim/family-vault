import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import Home from "@/app/page";
import { ChecklistView } from "@/components/ChecklistView";
import { toElements } from "@/components/EstateMap";
import { ApiError } from "@/lib/api";
import { checkFreeText, checkMaskedId } from "@/lib/masking";
import { SessionProvider } from "@/lib/session";
import type { Checklist, Graph } from "@/lib/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }), usePathname: () => "/" }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("masking mirror (same rules as the API)", () => {
  it.each(["1234", "XXXX1234", "****1234", "xx-xx-ab12"])("accepts %s", (v) => {
    expect(checkMaskedId(v).ok).toBe(true);
  });
  it.each(["123456789012", "50100234567890", "4111 1111 1111 1111", "XXXX12345"])("rejects full number %s", (v) => {
    const r = checkMaskedId(v);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.reason).toMatch(/last 4/);
  });
  it.each(["Aadhaar 1234 5678 9012", "PAN ABCDE1234F", "ATM PIN 4321", "net banking password is Tiger@123"])(
    "rejects secrets in free text: %s",
    (v) => expect(checkFreeText(v).ok).toBe(false),
  );
  it.each(["Blue file in cupboard", "Matures on 2026-11-20", "Pin it on the fridge"])("allows %s", (v) => {
    expect(checkFreeText(v).ok).toBe(true);
  });
  it("normalises to XXXX form", () => {
    expect(checkMaskedId("4471")).toEqual({ ok: true, value: "XXXX4471" });
  });
});

describe("ApiError", () => {
  it("surfaces the masking explanation", () => {
    const e = new ApiError(422, { error: "masked_input_required", reason: "this looks like a full number", why: "Only last 4." });
    expect(e.message).toContain("full number");
    expect(e.message).toContain("Only last 4.");
  });
});

describe("estate map elements", () => {
  const graph: Graph = {
    nodes: [
      { id: "p1", cls: "Person", props: { name: "Asha" }, provenance: { source: "t", timestamp: "", confidence: 1, method: "human" } },
      { id: "a1", cls: "Asset", props: { label: "FD" }, provenance: { source: "t", timestamp: "", confidence: 1, method: "human" } },
      { id: "d1", cls: "Document", props: { label: "Receipt" }, provenance: { source: "t", timestamp: "", confidence: 1, method: "human" } },
    ],
    edges: [
      { id: "p1|owns|a1", src: "p1", rel: "owns", dst: "a1", props: {} },
      { id: "a1|documented_by|d1", src: "a1", rel: "documented_by", dst: "d1", props: {} },
      { id: "p1|knows_about|a1", src: "p1", rel: "knows_about", dst: "a1", props: {} },
    ],
    visible_items: ["a1"],
    gaps_by_node: { a1: [{ key: "G01:a1", severity: "high", title: "No nominee" }] },
    as_of: "2026-11-01",
  };
  it("highlights gaps and hides documents/knows edges by default", () => {
    const els = toElements(graph, false, false);
    expect(els.map((e) => e.data.id)).toEqual(["p1", "a1", "p1|owns|a1"]);
    expect(els[1].data.gap).toBe("high");
  });
  it("can show everything", () => {
    expect(toElements(graph, true, true)).toHaveLength(6);
  });
});

describe("checklist view", () => {
  it("renders blocked steps, actors, documents and the disclaimer", () => {
    const cl: Checklist = {
      scenario: "death_of_earner",
      scenario_label: "Death",
      subject_id: "p1",
      subject_name: "Asha",
      disclaimer: "General guidance only — verify with the institution.",
      blocked_count: 1,
      steps: [
        { order: 1, action: "x", text: "Claim the FD", institution: "Fictional Bank", item_ids: ["a1"], required_documents: ["Death certificate"], actors: ["Ravi"], actor_ids: ["p2"], blocked: true, blocked_by: ["G01:a1"], notes: ["No nominee"] },
      ],
    };
    render(<ChecklistView cl={cl} />);
    expect(screen.getByText(/General guidance only/)).toBeTruthy();
    expect(screen.getByText("Blocked by a gap")).toBeTruthy();
    expect(screen.getByText("Death certificate")).toBeTruthy();
    expect(screen.getByText("Ravi")).toBeTruthy();
  });
});

describe("home page smoke", () => {
  it("lists sample families from the API with the demo warning", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify([{ id: "family_a", display_name: "Mehta family (synthetic)", story: "Young kids." }]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    render(
      <SessionProvider>
        <Home />
      </SessionProvider>,
    );
    await waitFor(() => expect(screen.getByText("Mehta family (synthetic)")).toBeTruthy());
    expect(screen.getByText(/Know where everything is/)).toBeTruthy();
    expect(screen.getByText("Start a new family")).toBeTruthy();
  });

  it("shows a friendly error when the API is down", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("offline"))));
    render(
      <SessionProvider>
        <Home />
      </SessionProvider>,
    );
    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/make demo/));
  });
});
