"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api } from "./api";
import type { Persona, Session } from "./types";

const KEY = "fv.session";
const OWNER_KEY = "fv.owner";

interface Ctx {
  session: Session | null;
  ready: boolean;
  ownerSession: Session | null;
  setSession: (s: Session | null) => void;
  switchTo: (p: Persona) => Promise<void>;
  backToOwner: () => void;
  lock: () => Promise<void>;
  /** Increment to tell pages that data changed (e.g. after a fix). */
  version: number;
  bump: () => void;
}

const SessionCtx = createContext<Ctx | null>(null);

function read(key: string): Session | null {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

function write(key: string, s: Session | null): void {
  try {
    if (s) sessionStorage.setItem(key, JSON.stringify(s));
    else sessionStorage.removeItem(key);
  } catch {
    /* storage unavailable: session lives in memory only */
  }
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSessionState] = useState<Session | null>(null);
  const [ownerSession, setOwner] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    setSessionState(read(KEY));
    setOwner(read(OWNER_KEY));
    setReady(true);
  }, []);

  const setSession = useCallback((s: Session | null) => {
    setSessionState(s);
    write(KEY, s);
    if (s?.principal.role === "owner") {
      setOwner(s);
      write(OWNER_KEY, s);
    }
    if (!s) {
      setOwner(null);
      write(OWNER_KEY, null);
    }
  }, []);

  const switchTo = useCallback(
    async (p: Persona) => {
      const owner = ownerSession ?? session;
      if (!owner) return;
      const s = await api<Session>("/session/act-as", { token: owner.token, body: p });
      setSessionState(s);
      write(KEY, s);
      setVersion((v) => v + 1);
    },
    [ownerSession, session],
  );

  const backToOwner = useCallback(() => {
    if (ownerSession) {
      setSessionState(ownerSession);
      write(KEY, ownerSession);
      setVersion((v) => v + 1);
    }
  }, [ownerSession]);

  const lock = useCallback(async () => {
    for (const s of [session, ownerSession]) {
      if (s) await api("/session", { method: "DELETE", token: s.token }).catch(() => undefined);
    }
    setSession(null);
  }, [session, ownerSession, setSession]);

  const value = useMemo(
    () => ({ session, ready, ownerSession, setSession, switchTo, backToOwner, lock, version, bump: () => setVersion((v) => v + 1) }),
    [session, ready, ownerSession, setSession, switchTo, backToOwner, lock, version],
  );
  return <SessionCtx.Provider value={value}>{children}</SessionCtx.Provider>;
}

export function useSession(): Ctx {
  const ctx = useContext(SessionCtx);
  if (!ctx) throw new Error("useSession must be used inside SessionProvider");
  return ctx;
}

export function isFull(s: Session | null): boolean {
  return !!s && (s.principal.role === "owner" || (s.principal.role === "spouse" && s.principal.spouse_scope === "full"));
}
