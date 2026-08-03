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
  return JSON.parse(text) as T;
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers ?? {});
  if (!headers.has("Content-Type") && options.body) {
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
    const err = body as ApiError;
    throw new ApiClientError(
      err?.error?.message ?? `Erreur HTTP ${response.status}`,
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
