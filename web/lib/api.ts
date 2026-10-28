export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  body: Record<string, unknown>;

  constructor(status: number, body: Record<string, unknown>) {
    super(ApiError.describe(status, body));
    this.status = status;
    this.body = body;
  }

  /** Human-friendly message, including the masking guard's explanation when present. */
  static describe(status: number, body: Record<string, unknown>): string {
    if (body.error === "masked_input_required") {
      return `${String(body.reason ?? "Not accepted")}. ${String(body.why ?? "")}`;
    }
    const detail = body.detail ?? body.error;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((d) => (d as { msg?: string }).msg ?? "").join("; ");
    if (status === 401) return "Your session ended. Please unlock the vault again.";
    return `Something went wrong (${status}).`;
  }
}

interface Opts {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  token?: string | null;
  raw?: boolean;
}

export async function api<T = unknown>(path: string, opts: Opts = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.token) headers.Authorization = `Bearer ${opts.token}`;
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method: opts.method ?? (opts.body !== undefined ? "POST" : "GET"),
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    throw new ApiError(0, { detail: "Cannot reach the family-vault API. Is `make demo` running?" });
  }
  if (!res.ok) {
    let body: Record<string, unknown> = {};
    try {
      body = await res.json();
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, body);
  }
  if (opts.raw) return (await res.blob()) as T;
  return (await res.json()) as T;
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
