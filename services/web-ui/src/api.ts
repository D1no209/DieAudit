export const API_KEY_STORAGE_KEY = "dieaudit.apiKey";
export const API_KEY_HEADER_STORAGE_KEY = "dieaudit.apiKeyHeader";
export const API_KEY_HEADER = "X-DieAudit-Api-Key";

export async function readJson<T = unknown>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, withAuth(options));
  const text = await response.text();
  if (!response.ok) {
    throw new Error(formatHttpError(text, response.statusText));
  }
  return (text ? JSON.parse(text) : {}) as T;
}

export function withAuth(options?: RequestInit): RequestInit {
  const headers = new Headers(options?.headers);
  const apiKey = getStoredApiKey();
  if (apiKey) {
    headers.set(apiKeyHeaderName(), apiKey);
  }
  return { ...options, headers };
}

export function getStoredApiKey() {
  return window.localStorage.getItem(API_KEY_STORAGE_KEY) || "";
}

export function storeApiKey(apiKey: string) {
  window.localStorage.setItem(API_KEY_STORAGE_KEY, apiKey);
}

export function clearStoredApiKey() {
  window.localStorage.removeItem(API_KEY_STORAGE_KEY);
}

export function apiKeyHeaderName() {
  const stored = window.localStorage.getItem(API_KEY_HEADER_STORAGE_KEY);
  if (stored && isValidHeaderName(stored)) {
    return stored;
  }
  if (stored) {
    window.localStorage.removeItem(API_KEY_HEADER_STORAGE_KEY);
  }
  return API_KEY_HEADER;
}

export function rememberApiKeyHeaderName(headerName?: string) {
  const normalized = (headerName || "").trim();
  if (normalized && isValidHeaderName(normalized)) {
    window.localStorage.setItem(API_KEY_HEADER_STORAGE_KEY, normalized);
  }
}

function isValidHeaderName(headerName: string) {
  try {
    new Headers({ [headerName]: "probe" });
    return true;
  } catch {
    return false;
  }
}

export function formatHttpError(body: string, fallback: string) {
  try {
    const parsed = JSON.parse(body);
    if (typeof parsed.detail === "string") {
      return parsed.detail;
    }
    if (parsed.detail) {
      return JSON.stringify(parsed.detail);
    }
    return JSON.stringify(parsed);
  } catch {
    return body || fallback;
  }
}
