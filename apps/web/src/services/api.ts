/** Authenticated API client. Tokens live in localStorage; all requests are
 * typed against the shared contracts in src/types/api.ts. */

const TOKEN_KEY = "lifesmart_token";
// Empty base = same-origin relative requests. This is what the packaged
// desktop app needs (the FastAPI binary serves the UI and the API together).
// In dev, set VITE_API_BASE_URL or rely on the Vite /api proxy.
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

/** Resolve a path against the configured base, or the current origin. */
function resolveUrl(path: string): string {
  if (BASE_URL) return BASE_URL + path;
  const origin =
    typeof window !== "undefined" ? window.location.origin : "http://localhost";
  return new URL(path, origin).toString();
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(
  path: string,
  options: {
    method?: string;
    body?: unknown;
    params?: Record<string, string | number | boolean | undefined>;
  } = {},
): Promise<T> {
  const url = new URL(resolveUrl(path));
  if (options.params) {
    for (const [k, v] of Object.entries(options.params)) {
      if (v !== undefined && v !== "") url.searchParams.set(k, String(v));
    }
  }
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  const resp = await fetch(url, {
    method: options.method ?? (options.body !== undefined ? "POST" : "GET"),
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const data = await resp.json();
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

/** Fetch an authenticated binary resource (asset thumbnails) as an object URL. */
export async function fetchObjectUrl(path: string): Promise<string> {
  const resp = await fetch(resolveUrl(path), {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!resp.ok) throw new ApiError(resp.status, "Failed to load image");
  const blob = await resp.blob();
  return URL.createObjectURL(blob);
}

/** Download an authenticated file (e.g. a CSV report export) and hand it to
 * the browser. Requests stay same-origin like every other API call. */
export async function downloadFile(
  path: string,
  params: Record<string, string | number | boolean | undefined> = {},
): Promise<void> {
  const url = new URL(resolveUrl(path));
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") url.searchParams.set(k, String(v));
  }
  const resp = await fetch(url, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!resp.ok) throw new ApiError(resp.status, "Download failed");
  const blob = await resp.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = "lifesmart-report.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}
