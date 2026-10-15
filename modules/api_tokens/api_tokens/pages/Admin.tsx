import { Head, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { InlineBanner } from '@simple-module-py/ui/components/InlineBanner';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { Building2, Plus } from 'lucide-react';
import { useState } from 'react';
import { CreatedTokenDialog } from './components/CreatedTokenDialog';
import { CreateTokenDialog } from './components/CreateTokenDialog';
import { RevokeTokenDialog } from './components/RevokeTokenDialog';
import { TokenTable } from './components/TokenTable';
import { useTokenActions } from './components/useTokenActions';
import type { CreatePayload, TokenFormProps } from './types';

interface Props extends TokenFormProps {
  roles: string[];
  tenant_required: boolean;
}

/** Every token in the active tenant; service keys are created here. */
function Admin() {
  const props = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();
  const [creating, setCreating] = useState(false);
  // An audit-log link lands here as ?token=<id>; mark that row.
  const highlightId =
    typeof window === 'undefined' ? null : new URLSearchParams(window.location.search).get('token');
  const actions = useTokenActions({
    csrfToken: props.csrf_token,
    createUrl: `${props.api_url}/admin/service-keys`,
    revokeUrl: (id) => `${props.api_url}/admin/tokens/${id}/revoke`,
  });

  async function submit(payload: CreatePayload) {
    const ok = await actions.create(payload);
    if (ok) setCreating(false);
    return ok;
  }

  return (
    <>
      <Head title={t(keys.api_tokens.admin.title)} />
      <PageShell
        title={t(keys.api_tokens.admin.title)}
        description={t(keys.api_tokens.admin.description)}
        actions={
          <Button onClick={() => setCreating(true)} disabled={props.tenant_required}>
            <Plus className="size-4" />
            {t(keys.api_tokens.admin.new_service_key)}
          </Button>
        }
      >
        {props.tenant_required ? (
          <InlineBanner
            icon={Building2}
            tone="warning"
            title={t(keys.api_tokens.admin.tenant_required)}
          />
        ) : (
          <TokenTable
            tokens={props.tokens}
            showOwner
            highlightId={highlightId}
            onRevoke={actions.setPendingRevoke}
          />
        )}
      </PageShell>

      <CreateTokenDialog
        open={creating}
        onOpenChange={setCreating}
        variant="service"
        scopes={props.scopes}
        roles={props.roles}
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
    </>
  );
}

Admin.layout = [AdminLayout];
export default Admin;
