// Auth API client — env-backed superadmin/multi-user login.
// Vite proxies /api → FastAPI. Cookie is httponly (set by backend); the SPA
// gates on GET /auth/me. Same-origin fetch sends the cookie automatically.

const base = '/api';

export type Me =
  | { authenticated: false; configured: boolean }
  | { authenticated: true; email: string; role: string };

export type LoginResult = { ok: boolean; email: string; role: string };

async function post<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(base + path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined
  });
  if (!r.ok) {
    let detail = `${path} → ${r.status}`;
    try { detail = (await r.json())?.detail ?? detail; } catch { /* ignore */ }
    throw new Error(detail);
  }
  return r.json();
}

export type SsoConfig = { enabled: boolean; provider: string; login_url: string };

export const authApi = {
  me: async (): Promise<Me> => {
    const r = await fetch(base + '/auth/me', { credentials: 'same-origin' });
    if (!r.ok) return { authenticated: false, configured: false };
    return r.json();
  },
  ssoConfig: async (): Promise<SsoConfig> => {
    try {
      const r = await fetch(base + '/auth/sso/config', { credentials: 'same-origin' });
      if (r.ok) return r.json();
    } catch { /* ignore */ }
    return { enabled: false, provider: 'SSO', login_url: '/api/auth/sso/login' };
  },
  login: (email: string, password: string, remember = false) =>
    post<LoginResult>('/auth/login', { email, password, remember }),
  logout: () => post<{ ok: boolean }>('/auth/logout')
};
