export interface ApiToken {
  id: string;
  kind: 'personal' | 'service';
  name: string;
  prefix: string;
  scopes: string[];
  roles: string[];
  owner_user_id: string | null;
  owner_email: string | null;
  tenant_id: string | null;
  created_at: string | null;
  expires_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

/** Props both pages receive for their create form. */
export interface TokenFormProps {
  tokens: ApiToken[];
  scopes: string[];
  max_lifetime_days: number;
  expiry_presets: number[];
  csrf_token: string;
  api_url: string;
}

export interface CreatePayload {
  name: string;
  scopes: string[];
  roles?: string[];
  expires_in_days: number;
}

export type TokenStatus = 'active' | 'revoked' | 'expired';

export function tokenStatus(token: ApiToken, now: number = Date.now()): TokenStatus {
  if (token.revoked_at) return 'revoked';
  if (new Date(token.expires_at).getTime() <= now) return 'expired';
  return 'active';
}
