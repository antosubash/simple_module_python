import { router } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import type { ApiResult } from '@simple-module-py/ui/lib/api';
import { useState } from 'react';
import { toast } from 'sonner';
import type { ApiToken, CreatePayload } from '../types';

/** The calls a page wires to its own endpoints (personal tokens or service keys). */
export interface TokenCalls {
  create: (payload: CreatePayload) => Promise<ApiResult<{ token: string }>>;
  revoke: (id: string) => Promise<ApiResult<unknown>>;
  /** Bulk revoke of every token the caller holds; omitted on the admin page. */
  revokeAll?: () => Promise<ApiResult<{ revoked: number }>>;
}

/** Create / revoke through the JSON API, then reload the page's `tokens` prop. */
export function useTokenActions({ create: createCall, revoke, revokeAll }: TokenCalls) {
  const { t } = useT();
  const [created, setCreated] = useState<string | null>(null);
  const [pendingRevoke, setPendingRevoke] = useState<ApiToken | null>(null);
  const [pendingRevokeAll, setPendingRevokeAll] = useState(false);
  const [busy, setBusy] = useState(false);

  async function create(payload: CreatePayload): Promise<boolean> {
    setBusy(true);
    const result = await createCall(payload);
    setBusy(false);
    if (!result.ok) {
      toast.error(result.detail ?? t(keys.api_tokens.toasts.failed));
      return false;
    }
    setCreated(result.data.token);
    router.reload({ only: ['tokens'] });
    return true;
  }

  async function confirmRevoke() {
    if (!pendingRevoke) return;
    setBusy(true);
    const result = await revoke(pendingRevoke.id);
    setBusy(false);
    setPendingRevoke(null);
    if (!result.ok) {
      toast.error(result.detail ?? t(keys.api_tokens.toasts.failed));
      return;
    }
    toast.success(t(keys.api_tokens.toasts.revoked));
    router.reload({ only: ['tokens'] });
  }

  async function confirmRevokeAll() {
    if (!revokeAll) return;
    setBusy(true);
    const result = await revokeAll();
    setBusy(false);
    setPendingRevokeAll(false);
    if (!result.ok) {
      toast.error(result.detail ?? t(keys.api_tokens.toasts.failed));
      return;
    }
    toast.success(t(keys.api_tokens.toasts.revoked_all, { count: result.data.revoked }));
    router.reload({ only: ['tokens'] });
  }

  return {
    busy,
    created,
    clearCreated: () => setCreated(null),
    create,
    pendingRevoke,
    setPendingRevoke,
    confirmRevoke,
    pendingRevokeAll,
    setPendingRevokeAll,
    confirmRevokeAll,
  };
}
