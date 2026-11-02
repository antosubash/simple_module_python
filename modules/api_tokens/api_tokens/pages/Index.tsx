import { Head } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { ConfirmActionDialog } from '@simple-module-py/ui/components/ConfirmActionDialog';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import { apiResult } from '@simple-module-py/ui/lib/api';
import { Ban, Plus } from 'lucide-react';
import { useState } from 'react';
import { api, csrfHeaders } from './api';
import { CreatedTokenDialog } from './components/CreatedTokenDialog';
import { CreateTokenDialog } from './components/CreateTokenDialog';
import { RevokeTokenDialog } from './components/RevokeTokenDialog';
import { TokenPagination } from './components/TokenPagination';
import { TokenTable } from './components/TokenTable';
import { useTokenActions } from './components/useTokenActions';
import { type CreatePayload, type TokenFormProps, tokenStatus } from './types';

/** Your own personal access tokens: list, create (secret shown once), revoke. */
function Index(props: TokenFormProps) {
  const { t } = useT();
  const [creating, setCreating] = useState(false);
  const headers = csrfHeaders(props.csrf_token);
  const actions = useTokenActions({
    create: (body) => apiResult(api.POST('/api/api_tokens/tokens/', { body, headers })),
    revoke: (id) =>
      apiResult(
        api.POST('/api/api_tokens/tokens/{token_id}/revoke', {
          params: { path: { token_id: id } },
          headers,
        }),
      ),
    revokeAll: () => apiResult(api.POST('/api/api_tokens/tokens/revoke-all', { headers })),
  });
  // Unseen pages may still contain live tokens.
  const hasLive =
    props.pagination.has_more ||
    props.pagination.offset > 0 ||
    props.tokens.some((tok) => tokenStatus(tok) === 'active');

  async function submit(payload: CreatePayload) {
    const ok = await actions.create(payload);
    if (ok) setCreating(false);
    return ok;
  }

  return (
    <>
      <Head title={t(keys.api_tokens.index.title)} />
      <PageShell
        title={t(keys.api_tokens.index.title)}
        description={t(keys.api_tokens.index.description)}
        actions={
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => actions.setPendingRevokeAll(true)}
              disabled={!hasLive}
            >
              <Ban className="size-4" />
              {t(keys.api_tokens.revoke_all.button)}
            </Button>
            <Button onClick={() => setCreating(true)} disabled={props.scopes.length === 0}>
              <Plus className="size-4" />
              {t(keys.api_tokens.form.new_token)}
            </Button>
          </div>
        }
      >
        <p className="text-sm text-muted-foreground">{t(keys.api_tokens.index.usage)}</p>
        <TokenTable tokens={props.tokens} onRevoke={actions.setPendingRevoke} />
        <TokenPagination {...props.pagination} />
      </PageShell>

      <CreateTokenDialog
        open={creating}
        onOpenChange={setCreating}
        variant="personal"
        scopes={props.scopes}
        expiryPresets={props.expiry_presets}
        busy={actions.busy}
        onSubmit={submit}
      />
      <CreatedTokenDialog token={actions.created} onClose={actions.clearCreated} />
      <RevokeTokenDialog
        token={actions.pendingRevoke}
        busy={actions.busy}
        onCancel={() => actions.setPendingRevoke(null)}
        onConfirm={actions.confirmRevoke}
      />
      <ConfirmActionDialog
        open={actions.pendingRevokeAll}
        onOpenChange={(open) => !open && actions.setPendingRevokeAll(false)}
        tone="destructive"
        icon={Ban}
        title={t(keys.api_tokens.revoke_all.title)}
        description={t(keys.api_tokens.revoke_all.description)}
        confirmLabel={t(keys.api_tokens.revoke_all.confirm)}
        cancelLabel={t(keys.api_tokens.revoke_all.cancel)}
        busy={actions.busy}
        onConfirm={actions.confirmRevokeAll}
      />
    </>
  );
}

Index.layout = [AuthenticatedLayout];
export default Index;
