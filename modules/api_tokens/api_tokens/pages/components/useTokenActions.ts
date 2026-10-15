import { router } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { useState } from 'react';
import { toast } from 'sonner';
import { postJson } from '../api';
import type { ApiToken, CreatePayload } from '../types';

interface Options {
  csrfToken: string;
  createUrl: string;
  revokeUrl: (id: string) => string;
}

interface Created {
  token: string;
  item: ApiToken;
}

/** Create / revoke through the JSON API, then reload the page's `tokens` prop. */
export function useTokenActions({ csrfToken, createUrl, revokeUrl }: Options) {
  const { t } = useT();
  const [created, setCreated] = useState<string | null>(null);
  const [pendingRevoke, setPendingRevoke] = useState<ApiToken | null>(null);
  const [busy, setBusy] = useState(false);

  async function create(payload: CreatePayload): Promise<boolean> {
    setBusy(true);
    const result = await postJson<Created>(createUrl, csrfToken, payload);
    setBusy(false);
    if (!result.ok || !result.data) {
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
    const result = await postJson<ApiToken>(revokeUrl(pendingRevoke.id), csrfToken);
    setBusy(false);
    setPendingRevoke(null);
    if (!result.ok) {
      toast.error(result.detail ?? t(keys.api_tokens.toasts.failed));
      return;
    }
    toast.success(t(keys.api_tokens.toasts.revoked));
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
  };
}
