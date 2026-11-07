import { ApiError, ApiErrorBody, networkError } from './errors';
import type { TokenResponseDto } from './types';

/**
 * Minimal fetch wrapper for the FastAPI backend.
 *
 * - The access token lives only in memory (never in localStorage).
 * - The refresh token is an HttpOnly cookie handled by the browser; every request uses
 *   `credentials: "include"` so the cookie reaches `/auth/*` endpoints.
 * - On a 401 the request is retried exactly once after a single, shared refresh call. The
 *   refresh endpoint itself never triggers a refresh, so there is no refresh loop.
 */

const DEFAULT_API_URL = 'http://localhost:8000/api/v1';
export const API_URL = (import.meta.env.VITE_API_URL || DEFAULT_API_URL).replace(/\/+$/, '');

let accessToken: string | null = null;
let refreshInFlight: Promise<TokenResponseDto | null> | null = null;

interface AuthListeners {
  /** Refresh failed (expired/revoked session): the app must drop its auth state. */
  onSessionExpired?: () => void;
  /** A refresh succeeded; the response carries the current user. */
  onTokenRefreshed?: (response: TokenResponseDto) => void;
}

let listeners: AuthListeners = {};

export function setAuthListeners(next: AuthListeners): void {
  listeners = next;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function hasAccessToken(): boolean {
  return accessToken !== null;
}

type QueryValue = string | number | boolean | null | undefined;

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  query?: Record<string, QueryValue> | object;
  /** Attach the bearer token and refresh on 401 (default true). */
  auth?: boolean;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = new URL(`${API_URL}${path}`, window.location.origin);
  if (query) {
    for (const [key, value] of Object.entries(query as Record<string, QueryValue>)) {
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

async function send(path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  if (options.auth !== false && accessToken) headers.Authorization = `Bearer ${accessToken}`;
  try {
    return await fetch(buildUrl(path, options.query), {
      method: options.method ?? 'GET',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      credentials: 'include',
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw networkError(error);
  }
}

async function parse<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  const data: unknown = text ? JSON.parse(text) : undefined;
  if (!response.ok) {
    const body = (data as { error?: ApiErrorBody } | undefined)?.error;
    throw new ApiError(
      response.status,
      body ?? { code: `HTTP_${response.status}`, message: response.statusText || 'Request failed' },
    );
  }
  return data as T;
}

async function doRefresh(): Promise<TokenResponseDto | null> {
  const response = await send('/auth/refresh', { method: 'POST', auth: false });
  if (response.status === 401 || response.status === 403) {
    accessToken = null;
    return null;
  }
  const data = await parse<TokenResponseDto>(response);
  accessToken = data.access_token;
  return data;
}

/**
 * Exchange the refresh cookie for a new access token. Concurrent callers share one request;
 * across browser tabs the Web Locks API serialises refreshes so two tabs never present the
 * same refresh token (which the server would treat as token theft).
 */
function withCrossTabLock<T>(fn: () => Promise<T>): Promise<T> {
  const locks = typeof navigator !== 'undefined' ? navigator.locks : undefined;
  if (!locks) return fn();
  return new Promise<T>((resolve, reject) => {
    // The lock is held until the callback's promise settles.
    locks.request('librarium-auth-refresh', () => fn().then(resolve, reject)).catch(reject);
  });
}

export function refreshSession(): Promise<TokenResponseDto | null> {
  if (!refreshInFlight) {
    refreshInFlight = withCrossTabLock(doRefresh)
      .then((data) => {
        if (data) listeners.onTokenRefreshed?.(data);
        return data;
      })
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

/** Like apiRequest, for file downloads (CSV exports): returns the body as a Blob. */
export async function apiDownload(path: string, options: Omit<RequestOptions, 'body'> = {}): Promise<Blob> {
  let response = await send(path, options);
  if (response.status === 401 && options.auth !== false) {
    const refreshed = await refreshSession();
    if (!refreshed) {
      listeners.onSessionExpired?.();
      return parse<never>(response);
    }
    response = await send(path, options);
  }
  if (!response.ok) return parse<never>(response); // throws ApiError
  return response.blob();
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let response = await send(path, options);
  if (response.status === 401 && options.auth !== false) {
    const refreshed = await refreshSession();
    if (!refreshed) {
      listeners.onSessionExpired?.();
      return parse<T>(response);
    }
    response = await send(path, options); // single retry; a second 401 is returned as is
  }
  return parse<T>(response);
}
