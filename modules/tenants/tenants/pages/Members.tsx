import { Head, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import { type Invitation, InvitationsList } from '../components/InvitationsList';
import { InviteForm } from '../components/InviteForm';
import { type Member, type MembershipRole, MembersTable } from '../components/MembersTable';

interface Tenant {
  id: string;
  name: string;
  slug: string;
}

interface Seats {
  used: number;
  limit: number | null;
}

interface Props {
  tenant: Tenant;
  my_role: MembershipRole;
  my_user_id: string;
  can_manage: boolean;
  members: Member[];
  invitations: Invitation[];
  seats: Seats;
}

function Members() {
  const { tenant, my_role, my_user_id, can_manage, members, invitations, seats } = usePage<{
    props: Props;
  }>().props as unknown as Props;
  const { t } = useT();

  function reload() {
    router.reload();
  }

  const seatsLine =
    seats.limit === null
      ? t(keys.tenants.members.seats_unlimited, { used: seats.used })
      : t(keys.tenants.members.seats_used, { used: seats.used, limit: seats.limit });

  return (
    <>
      <Head title={t(keys.tenants.members.head_title)} />
      <PageShell
        title={t(keys.tenants.members.title)}
        description={t(keys.tenants.members.description, { name: tenant.name })}
      >
        <div className="space-y-6">
          <Card className="overflow-hidden p-0">
            <MembersTable
              members={members}
              myRole={my_role}
              myUserId={my_user_id}
              canManage={can_manage}
              tenantName={tenant.name}
              onChanged={reload}
            />
            <div className="border-t px-4 py-3 text-sm text-muted-foreground">{seatsLine}</div>
          </Card>

          {can_manage && (
            <>
              <InviteForm onInvited={reload} />
              <InvitationsList invitations={invitations} onChanged={reload} />
            </>
          )}
        </div>
      </PageShell>
    </>
  );
}

Members.layout = [AuthenticatedLayout];
export default Members;
