"use client";

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "./api";
import { useSession } from "./session";

/** Fetch `path` with the current session token; refetches when the session or data version changes. */
export function useApi<T>(path: string | null) {
  const { session, version, setSession } = useSession();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const token = session?.token;

  const load = useCallback(async () => {
    if (!path || !token) return;
    setLoading(true);
    try {
      setData(await api<T>(path, { token }));
      setError(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setSession(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [path, token, setSession]);

  useEffect(() => {
    void load();
  }, [load, version]);

  return { data, error, loading, reload: load };
}
