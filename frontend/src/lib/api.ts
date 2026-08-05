import type { ApiError, ApiSuccess } from "@/types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";

export class ApiClientError extends Error {
  status: number;
  payload: ApiError | null;

  constructor(message: string, status: number, payload: ApiError | null = null) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.payload = payload;
  }
}

type TokenGetter = () => string | null;
type TokenClearer = () => void;

let getAccessToken: TokenGetter = () => null;
let clearAuth: TokenClearer = () => undefined;

export function configureApiAuth(getter: TokenGetter, clearer: TokenClearer) {
  getAccessToken = getter;
  clearAuth = clearer;
}

async function parseJson<T>(response: Response): Promise<T> {
  const text = await response.text();
  if (!text) {
    return {} as T;
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    return { raw: text } as T;
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const maxAttempts =
    options.method && options.method.toUpperCase() !== "GET" ? 3 : 2;
  let lastError: unknown;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await apiRequestOnce<T>(path, options);
    } catch (err) {
      lastError = err;
      const retryable =
        err instanceof ApiClientError &&
        (err.status === 502 || err.status === 503 || err.status === 0) &&
        // Ne pas réessayer une erreur métier renvoyée en 502 (start Python, etc.)
        !(err.payload?.error?.message);
      if (!retryable || attempt === maxAttempts) {
        throw err;
      }
      await new Promise((r) => setTimeout(r, 400 * attempt));
    }
  }
  throw lastError;
}

async function apiRequestOnce<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers ?? {});
  if (!headers.has("Content-Type") && options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const token = getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
    });
  } catch (err) {
    const raw = err instanceof Error ? err.message : String(err);
    const hint =
      /failed to fetch|networkerror|load failed|network request failed/i.test(raw)
        ? "Connexion interrompue (nginx ou API en redémarrage). Réessayez dans quelques secondes."
        : raw || "Erreur réseau";
    throw new ApiClientError(hint, 0, null);
  }

  if (response.status === 401) {
    clearAuth();
  }

  const body = await parseJson<ApiSuccess<T> | ApiError | T>(response);

  if (!response.ok) {
    const err = body as ApiError & { raw?: string };
    const code = err?.error?.code ?? "";
    if (response.status === 403 && code === "must_change_password") {
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/change-password")) {
        window.location.assign("/change-password");
      }
    }
    const messageRaw =
      err?.error?.message ||
      (typeof err?.error?.extra?.stderr === "string" ? err.error.extra.stderr : "") ||
      (typeof err?.error?.extra?.error === "string" ? err.error.extra.error : "") ||
      (typeof err?.raw === "string" ? err.raw : "") ||
      `Erreur HTTP ${response.status}`;
    let message = messageRaw
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 400) || `Erreur HTTP ${response.status}`;
    // 502/503 nginx (HTML/vide) ≠ erreur métier JSON de l'API (ex. start Python échoué).
    const hasApiError = Boolean(err?.error?.message || err?.success === false);
    if ((response.status === 502 || response.status === 503) && !hasApiError) {
      message =
        "API indisponible (502). Le service vzone-api est probablement arrêté ou en redémarrage. " +
        "Sur le serveur : sudo bash /opt/vzone-src/scripts/repair-api-502.sh — puis réessayez.";
    }
    throw new ApiClientError(
      message,
      response.status,
      err?.success === false ? err : null,
    );
  }

  if (body && typeof body === "object" && "success" in body && (body as { success: boolean }).success === true) {
    const successBody = body as ApiSuccess<T> & { results?: T };
    if ("data" in successBody && successBody.data !== undefined) {
      return successBody.data;
    }
    if ("results" in successBody && successBody.results !== undefined) {
      return successBody.results as T;
    }
  }

  return body as T;
}
