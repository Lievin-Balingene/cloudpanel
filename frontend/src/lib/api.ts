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
  const headers = new Headers(options.headers ?? {});
  if (!headers.has("Content-Type") && options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const token = getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

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
      (typeof err?.raw === "string" ? err.raw : "") ||
      `Erreur HTTP ${response.status}`;
    let message = messageRaw
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 240) || `Erreur HTTP ${response.status}`;
    if (
      response.status === 502 &&
      /bad gateway|nginx/i.test(message)
    ) {
      message =
        "502 Bad Gateway : l’API a été coupée pendant l’opération (souvent un reload SSL). " +
        "Vérifiez si le certificat est déjà actif, puis réessayez si besoin.";
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
