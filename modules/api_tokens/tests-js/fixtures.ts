import { vi } from 'vitest';
import type { ApiToken } from '../api_tokens/pages/types';

export function token(over: Partial<ApiToken> = {}): ApiToken {
  return {
    id: 't1',
    kind: 'personal',
    name: 'ci-token',
    prefix: 'smpy_ab12',
    scopes: ['files.read'],
    roles: [],
    owner_user_id: 'u1',
    owner_email: 'a@example.com',
    tenant_id: null,
    created_at: '2026-01-01T00:00:00Z',
    expires_at: '2999-01-01T00:00:00Z',
    last_used_at: null,
    revoked_at: null,
    ...over,
  };
}

export function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}
