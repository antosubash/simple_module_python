import { Head, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { EmptyState } from '@simple-module-py/ui/components/EmptyState';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import { Building2 } from 'lucide-react';
import { CreateOrgForm } from '../components/CreateOrgForm';
import { type Membership, MembershipList } from '../components/MembershipList';

interface Props {
  memberships: Membership[];
  active_id: string | null;
  suspended: boolean;
  can_create: boolean;
  reason: string | null;
}

function Index() {
  const { memberships, active_id, suspended, can_create, reason } = usePage<{ props: Props }>()
    .props as unknown as Props;
  const { t } = useT();

  function reload() {
    router.reload();
  }

  return (
    <>
      <Head title={t(keys.tenants.index.head_title)} />
      <PageShell
        title={t(keys.tenants.index.title)}
        description={t(keys.tenants.index.description)}
      >
        {reason === 'tenant_required' && (
          <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-700">
            {t(keys.tenants.index.notice_tenant_required)}
          </div>
        )}
        {suspended && !active_id && (
          <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-destructive">
            {t(keys.tenants.index.notice_suspended)}
          </div>
        )}

        <div className="space-y-6">
          {memberships.length === 0 ? (
            <EmptyState
              icon={Building2}
              title={t(keys.tenants.index.empty_title)}
              description={t(keys.tenants.index.empty_description)}
            />
          ) : (
            <MembershipList memberships={memberships} activeId={active_id} onSwitched={reload} />
          )}

          {can_create && <CreateOrgForm onCreated={reload} />}
        </div>
      </PageShell>
    </>
  );
}

Index.layout = [AuthenticatedLayout];
export default Index;
