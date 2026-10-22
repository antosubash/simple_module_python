import { Head, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { ConfirmActionDialog } from '@simple-module-py/ui/components/ConfirmActionDialog';
import { InlineBanner } from '@simple-module-py/ui/components/InlineBanner';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { PaginationBar } from '@simple-module-py/ui/components/PaginationBar';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { Building2, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { ShareTable } from './components/ShareTable';
import type { Share } from './types';

interface Props {
  shares: Share[];
  total: number;
  page: number;
  per_page: number;
  can_revoke: boolean;
  tenant_required: boolean;
}

const BASE_URL = '/admin/sharing';

/** Every share in the active tenant; admins may revoke any of them. */
function Admin() {
  const props = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();
  const [pending, setPending] = useState<Share | null>(null);
  const [busy, setBusy] = useState(false);
  // An audit-log link lands here as ?share=<id>; mark that row.
  const highlightId =
    typeof window === 'undefined' ? null : new URLSearchParams(window.location.search).get('share');

  function goTo(page: number) {
    router.get(`${BASE_URL}/`, { page }, { preserveScroll: true });
  }

  function confirmRevoke() {
    if (!pending) return;
    setBusy(true);
    router.post(
      `${BASE_URL}/${pending.id}/revoke`,
      {},
      {
        preserveScroll: true,
        onFinish: () => {
          setBusy(false);
          setPending(null);
        },
      },
    );
  }

  return (
    <>
      <Head title={t(keys.sharing.admin.title)} />
      <PageShell
        title={t(keys.sharing.admin.title)}
        description={t(keys.sharing.admin.description)}
      >
        {props.tenant_required ? (
          <InlineBanner
            icon={Building2}
            tone="warning"
            title={t(keys.sharing.admin.tenant_required)}
          />
        ) : (
          <>
            <ShareTable
              shares={props.shares}
              canRevoke={props.can_revoke}
              highlightId={highlightId}
              onRevoke={setPending}
            />
            <PaginationBar
              page={props.page}
              perPage={props.per_page}
              total={props.total}
              onPageChange={goTo}
              hideWhenSinglePage
            />
          </>
        )}
      </PageShell>
      <ConfirmActionDialog
        open={pending !== null}
        onOpenChange={(open) => !open && setPending(null)}
        icon={Trash2}
        title={t(keys.sharing.revoke.title)}
        description={t(keys.sharing.revoke.description)}
        confirmLabel={t(keys.sharing.revoke.confirm)}
        cancelLabel={t(keys.sharing.revoke.cancel)}
        onConfirm={confirmRevoke}
        busy={busy}
      />
    </>
  );
}

Admin.layout = [AdminLayout];
export default Admin;
