"use client";

import { Shell } from "@/components/Shell";
import { ErrorBox, GuidanceNote, Loading, PageTitle } from "@/components/ui";
import { useSession } from "@/lib/session";
import type { Item, Persona } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const TYPE: Record<string, string> = {
  insurance: "Insurance policy",
  fixed_deposit: "Fixed deposit",
  bank_account: "Bank account",
  demat: "Demat (shares)",
  mutual_fund: "Mutual fund",
  property: "Property",
  vehicle: "Vehicle",
  other: "Other",
};

function OwnerPreview() {
  const { switchTo } = useSession();
  const personas = useApi<Persona[]>("/session/personas");
  if (!personas.data) return <Loading />;
  const nominees = personas.data.filter((p) => p.role === "nominee");
  return (
    <>
      <PageTitle title="Nominee view" sub="See exactly what a nominee would see: only the assets they are nominee on, read-only, without private notes." />
      <div className="grid gap-3 md:grid-cols-3">
        {nominees.map((p) => (
          <button key={p.person_id} className="btn-secondary justify-start text-left" onClick={() => void switchTo(p)}>
            View as {p.label}
          </button>
        ))}
      </div>
    </>
  );
}

function NomineeAssets() {
  const { session } = useSession();
  const assets = useApi<Item[]>("/assets");
  if (assets.error) return <ErrorBox message={assets.error} />;
  if (!assets.data) return <Loading />;
  const emergency = session?.principal.role === "emergency";
  return (
    <>
      <PageTitle
        title={emergency ? "Emergency access (read-only)" : "What you are nominee for"}
        sub="This view is read-only and limited to the assets where you are the registered nominee."
      />
      <GuidanceNote text="If something happens, contact each institution below with the death certificate and the papers listed. Keep this page handy — you can print it." />
      <ul className="mt-5 grid gap-4 md:grid-cols-2">
        {assets.data.map((a) => (
          <li key={a.id} className="card">
            <p className="text-sm uppercase tracking-wide text-muted">{TYPE[String(a.props.asset_type)] ?? "Asset"}</p>
            <h2 className="text-xl font-bold">{String(a.props.label)}</h2>
            <dl className="mt-2 space-y-1">
              <div>
                <dt className="inline text-muted">Held at: </dt>
                <dd className="inline font-semibold">{a.links?.institution?.name ?? "Not recorded"}</dd>
              </div>
              {a.props.masked_id !== undefined && (
                <div>
                  <dt className="inline text-muted">Number ends in: </dt>
                  <dd className="inline font-semibold">{String(a.props.masked_id).replace("XXXX", "")}</dd>
                </div>
              )}
              <div>
                <dt className="inline text-muted">Owner: </dt>
                <dd className="inline font-semibold">{a.links?.owners.map((o) => o.name).join(", ")}</dd>
              </div>
            </dl>
            <h3 className="mt-3 font-bold">Papers</h3>
            {a.links?.documents.length ? (
              <ul className="ml-5 list-disc">
                {a.links.documents.map((d) => (
                  <li key={d.id}>
                    {String(d.props.label)}
                    {d.props.location ? ` — kept at: ${String(d.props.location)}` : ""}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sev-critical">No papers recorded — ask the owner where they are.</p>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}

function NomineePage() {
  const { session } = useSession();
  if (session?.principal.role === "owner") return <OwnerPreview />;
  return <NomineeAssets />;
}

export default function Page() {
  return (
    <Shell>
      <NomineePage />
    </Shell>
  );
}
