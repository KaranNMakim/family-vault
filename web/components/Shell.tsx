"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { Persona, Role } from "@/lib/types";

import { ShieldIcon } from "./Security";
import { ErrorBox, Loading } from "./ui";

const NAV: { href: string; label: string; roles: Role[] }[] = [
  { href: "/dashboard", label: "Overview", roles: ["owner", "spouse"] },
  { href: "/onboarding", label: "Add details", roles: ["owner", "spouse"] },
  { href: "/map", label: "Estate map", roles: ["owner", "spouse", "nominee", "advisor", "emergency"] },
  { href: "/gaps", label: "Gaps", roles: ["owner", "spouse", "advisor"] },
  { href: "/checklist", label: "If something happens", roles: ["owner", "spouse", "nominee", "emergency"] },
  { href: "/nominee", label: "Nominee view", roles: ["owner", "nominee", "emergency"] },
  { href: "/emergency", label: "Emergency access", roles: ["owner", "nominee"] },
  { href: "/vault", label: "Vault & audit", roles: ["owner"] },
];

const ROLE_LABEL: Record<Role, string> = {
  owner: "Owner",
  spouse: "Spouse",
  nominee: "Nominee (read-only)",
  advisor: "Advisor (read-only)",
  emergency: "Emergency access (read-only)",
};

function RoleSwitcher() {
  const { session, ownerSession, switchTo, backToOwner } = useSession();
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [error, setError] = useState<string | null>(null);
  const owner = ownerSession ?? (session?.principal.role === "owner" ? session : null);

  useEffect(() => {
    if (!owner) return;
    api<Persona[]>("/session/personas", { token: owner.token })
      .then(setPersonas)
      .catch(() => setPersonas([]));
  }, [owner, session?.token]);

  if (!owner || !session) return null;
  const current = personas.findIndex(
    (p) =>
      p.role === session.principal.role &&
      (p.person_id ?? null) === (session.principal.person_id ?? null) &&
      (p.advisor_id ?? null) === (session.principal.advisor_id ?? null),
  );
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="font-semibold text-muted">Preview as (demo)</span>
      <select
        aria-label="Switch role (demo)"
        className="field min-h-10 w-auto py-1"
        value={current < 0 ? "" : String(current)}
        onChange={async (e) => {
          const p = personas[Number(e.target.value)];
          setError(null);
          try {
            if (p.role === "owner") backToOwner();
            else await switchTo(p);
          } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
          }
        }}
      >
        {current < 0 && <option value="">{ROLE_LABEL[session.principal.role]}</option>}
        {personas.map((p, i) => (
          <option key={`${p.role}-${p.person_id ?? p.advisor_id}`} value={i}>
            {p.label}
          </option>
        ))}
      </select>
      {error && <span className="text-sev-critical">{error}</span>}
    </label>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const { session, ready, lock } = useSession();
  const router = useRouter();
  const path = usePathname();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (ready && !session) router.replace("/");
  }, [ready, session, router]);

  // Auto-lock after inactivity (mirrors the server's idle timeout).
  const idleMinutes = session?.security?.idle_timeout_minutes ?? 15;
  useEffect(() => {
    if (!session) return;
    let last = Date.now();
    const bump = () => {
      last = Date.now();
    };
    const events = ["mousemove", "keydown", "click", "touchstart", "scroll"] as const;
    events.forEach((e) => window.addEventListener(e, bump, { passive: true }));
    const id = setInterval(() => {
      if (Date.now() - last > idleMinutes * 60_000) void lock().then(() => router.push("/"));
    }, 15_000);
    return () => {
      events.forEach((e) => window.removeEventListener(e, bump));
      clearInterval(id);
    };
  }, [session, idleMinutes, lock, router]);

  if (!ready) return <Loading />;
  if (!session) return <ErrorBox message="The vault is locked. Taking you to the start page…" />;
  const role = session.principal.role;
  const items = NAV.filter((n) => n.roles.includes(role));

  return (
    <div>
      <header className="border-b border-line bg-card">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div>
            <Link href="/" className="text-xl font-bold text-brand">
              family-vault
            </Link>
            <div className="text-sm text-muted">
              {session.family.display_name} · <span className="font-semibold">{ROLE_LABEL[role]}</span>
            </div>
            <div className="mt-1 flex items-center gap-1.5 text-xs font-semibold text-brand" title={session.security?.encryption}>
              <ShieldIcon className="size-4" />
              {session.security?.two_factor ? "Unlocked with 2-step verification" : "Unlocked"} · auto-locks after {idleMinutes} min idle
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <RoleSwitcher />
            <button className="btn-secondary min-h-10 py-1" onClick={() => void lock().then(() => router.push("/"))}>
              Lock vault
            </button>
            <button className="btn-secondary min-h-10 py-1 md:hidden" aria-expanded={open} onClick={() => setOpen(!open)}>
              Menu
            </button>
          </div>
        </div>
        <nav className={`${open ? "block" : "hidden"} border-t border-line md:block`} aria-label="Main">
          <ul className="mx-auto flex max-w-6xl flex-col gap-1 px-2 py-2 md:flex-row md:flex-wrap">
            {items.map((n) => (
              <li key={n.href}>
                <Link
                  href={n.href}
                  onClick={() => setOpen(false)}
                  className={`block rounded-lg px-3 py-2 font-semibold ${
                    path === n.href ? "bg-brand text-white" : "text-ink hover:bg-brand-soft"
                  }`}
                  aria-current={path === n.href ? "page" : undefined}
                >
                  {n.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
    </div>
  );
}
