export const API_KEY_STORAGE_KEY = "dieaudit.apiKey";
export const API_KEY_HEADER = "X-DieAudit-Api-Key";

export async function readJson(path: string, options?: RequestInit) {
  const response = await fetch(path, withAuth(options));
  const text = await response.text();
  if (!response.ok) {
    throw new Error(formatHttpError(text, response.statusText));
  }
  return text ? JSON.parse(text) : {};
}

export function withAuth(options?: RequestInit): RequestInit {
  const headers = new Headers(options?.headers);
  const apiKey = window.localStorage.getItem(API_KEY_STORAGE_KEY);
  if (apiKey) {
    headers.set(API_KEY_HEADER, apiKey);
  }
  return { ...options, headers };
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
