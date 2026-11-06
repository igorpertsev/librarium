import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { API_URL, apiRequest, setAccessToken, setAuthListeners } from './client';
import { ApiError } from './errors';

type Handler = (url: string, init: RequestInit) => Response | Promise<Response>;

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const tokenResponse = (token: string) =>
  json(200, { access_token: token, token_type: 'bearer', expires_in: 900, user: { id: 'u1' } });

function mockFetch(handler: Handler) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
    Promise.resolve(handler(String(input), init ?? {})),
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

const authHeader = (init: RequestInit) =>
  (init.headers as Record<string, string> | undefined)?.Authorization;

describe('apiRequest', () => {
  beforeEach(() => {
    setAccessToken('expired-token');
    setAuthListeners({});
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    setAccessToken(null);
  });

  it('sends the bearer token and the cookie', async () => {
    const fetchMock = mockFetch(() => json(200, { ok: true }));
    await expect(apiRequest('/books', { query: { page: 2, search: '' } })).resolves.toEqual({ ok: true });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${API_URL}/books?page=2`);
    expect(authHeader(init!)).toBe('Bearer expired-token');
    expect(init!.credentials).toBe('include');
  });

  it('refreshes once on 401 and retries the request with the new token', async () => {
    const onTokenRefreshed = vi.fn();
    setAuthListeners({ onTokenRefreshed });
    const fetchMock = mockFetch((url, init) => {
      if (url.endsWith('/auth/refresh')) return tokenResponse('fresh-token');
      return authHeader(init) === 'Bearer fresh-token' ? json(200, { items: [] }) : json(401, {});
    });

    // Two requests fail at the same time: they share a single refresh call.
    const [a, b] = await Promise.all([apiRequest('/cart'), apiRequest('/orders')]);
    expect(a).toEqual({ items: [] });
    expect(b).toEqual({ items: [] });
    const refreshCalls = fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/auth/refresh'));
    expect(refreshCalls).toHaveLength(1);
    expect(authHeader(refreshCalls[0][1]!)).toBeUndefined(); // the cookie authenticates refresh
    expect(onTokenRefreshed).toHaveBeenCalledTimes(1);
  });

  it('reports an expired session when the refresh fails', async () => {
    const onSessionExpired = vi.fn();
    setAuthListeners({ onSessionExpired });
    mockFetch((url) =>
      url.endsWith('/auth/refresh')
        ? json(401, { error: { code: 'REFRESH_TOKEN_INVALID', message: 'Invalid' } })
        : json(401, { error: { code: 'TOKEN_EXPIRED', message: 'Expired' } }),
    );

    const error = await apiRequest('/cart').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe('TOKEN_EXPIRED');
    expect(onSessionExpired).toHaveBeenCalledTimes(1);
  });

  it('does not refresh for requests made without auth', async () => {
    const fetchMock = mockFetch(() =>
      json(401, { error: { code: 'INVALID_CREDENTIALS', message: 'Invalid email or password' } }),
    );
    const error = await apiRequest('/auth/login', { method: 'POST', body: {}, auth: false }).catch(
      (e: unknown) => e,
    );
    expect((error as ApiError).code).toBe('INVALID_CREDENTIALS');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('turns network failures into NETWORK_ERROR', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))));
    const error = await apiRequest('/books').catch((e: unknown) => e);
    expect((error as ApiError).code).toBe('NETWORK_ERROR');
    expect((error as ApiError).status).toBe(0);
  });

  it('returns undefined for 204 responses', async () => {
    mockFetch(() => new Response(null, { status: 204 }));
    await expect(apiRequest('/cart', { method: 'DELETE' })).resolves.toBeUndefined();
  });
});
