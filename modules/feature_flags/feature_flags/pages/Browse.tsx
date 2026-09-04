import { Head, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { usePermissions } from '@simple-module-py/ui/hooks/use-permissions';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { useState } from 'react';
import { toast } from 'sonner';
import { FlagTable } from './components/FlagTable';
import { ScopeCard } from './components/ScopeCard';
import { type PendingToggle, ToggleConfirmDialog } from './components/ToggleConfirmDialog';
import type { FeatureFlag } from './types';

interface Props {
  flags: FeatureFlag[];
  tenant_id: string | null;
  tenants: string[];
  audit_log_url: string | null;
}

function buildPath(tenantId: string | null) {
  // Trailing slash: the browse route is registered at "/" under the module's
  // view prefix, and `_clone_bare_prefix_route` cannot alias a bare prefix for
  // routes contributed via `include_router` — so the bare form costs a 307 on
  // every navigation. Matches MENU_URL in constants.py.
  return tenantId
    ? `/admin/feature-flags/?tenant_id=${encodeURIComponent(tenantId)}`
    : '/admin/feature-flags/';
}

function actionUrl(name: string, action: 'toggle' | 'clear', tenantId: string | null) {
  const base = `/admin/feature-flags/${name}/${action}`;
  return tenantId ? `${base}?tenant_id=${encodeURIComponent(tenantId)}` : base;
}

function Browse() {
  const { flags, tenant_id, tenants, audit_log_url } = usePage<{ props: Props }>()
    .props as unknown as Props;
  const { t } = useT();
  const { can } = usePermissions();
  const canManage = can('feature_flags.manage');

  // The switch stages the change; the confirm is what writes it. The Switch
  // stays bound to the server value, so cancelling leaves it where it was
  // without needing to undo anything.
  const [pending, setPending] = useState<PendingToggle | null>(null);

  function handleToggle({ name, next }: PendingToggle) {
    setPending(null);
    router.post(
      actionUrl(name, 'toggle', tenant_id),
      { enabled: next },
      {
        preserveScroll: true,
        onSuccess: () =>
          toast.success(
            next
              ? t(keys.feature_flags.toasts.enabled, { name })
              : t(keys.feature_flags.toasts.disabled, { name }),
          ),
        onError: () => toast.error(t(keys.feature_flags.toasts.toggle_failed)),
      },
    );
  }

  function handleClear(flag: FeatureFlag) {
    router.post(
      actionUrl(flag.name, 'clear', tenant_id),
      {},
      {
        preserveScroll: true,
        onSuccess: () => toast.success(t(keys.feature_flags.toasts.cleared, { name: flag.name })),
        onError: () => toast.error(t(keys.feature_flags.toasts.toggle_failed)),
      },
    );
  }

  return (
    <>
      <Head title={t(keys.feature_flags.browse.title)} />
      <PageShell
        title={t(keys.feature_flags.browse.title)}
        description={t(keys.feature_flags.browse.description)}
      >
        <ScopeCard
          tenantId={tenant_id}
          tenants={tenants}
          auditLogUrl={audit_log_url}
          onSelect={(next) => router.visit(buildPath(next))}
        />

        <FlagTable
          flags={flags}
          tenantId={tenant_id}
          canManage={canManage}
          onToggle={(flag, next) => setPending({ name: flag.name, next })}
          onClear={handleClear}
        />

        <ToggleConfirmDialog
          pending={pending}
          tenantId={tenant_id}
          onConfirm={handleToggle}
          onCancel={() => setPending(null)}
        />
      </PageShell>
    </>
  );
}

Browse.layout = (page: React.ReactNode) => <AdminLayout>{page}</AdminLayout>;
export default Browse;
