import { API_KEY_HEADER_STORAGE_KEY, API_KEY_STORAGE_KEY, API_KEY_HEADER, formatHttpError } from "../api";

export type BffError = {
  error: {
    code: string;
    message: string;
    request_id?: string;
    details?: Record<string, unknown>;
  };
};

export async function bffGet<T>(path: string): Promise<T> {
  return bffRequest<T>(path);
}

export async function bffPost<T>(path: string, body?: unknown): Promise<T> {
  return bffRequest<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
}

export async function bffRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api/bff${path}`, withBffAuth(options));
  const text = await response.text();
  if (!response.ok) {
    throw new Error(formatBffError(text, response.statusText));
  }
  return (text ? JSON.parse(text) : {}) as T;
}

export function withBffAuth(options?: RequestInit): RequestInit {
  const headers = new Headers(options?.headers);
  const apiKey = window.localStorage.getItem(API_KEY_STORAGE_KEY);
  if (apiKey) {
    headers.set(apiKeyHeaderName(), apiKey);
  }
  return { ...options, headers };
}

function apiKeyHeaderName() {
  return window.localStorage.getItem(API_KEY_HEADER_STORAGE_KEY) || API_KEY_HEADER;
}

function formatBffError(body: string, fallback: string) {
  try {
    const parsed = JSON.parse(body) as BffError;
    if (parsed.error?.message) {
      return parsed.error.message;
    }
  } catch {
    return formatHttpError(body, fallback);
  }
  return fallback;
}
