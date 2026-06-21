import { Link, router, usePage } from '@inertiajs/react';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import { ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import { AccountStatusCard } from './components/AccountStatusCard';
import { DangerZone } from './components/DangerZone';
import { DetailsCard } from './components/DetailsCard';

interface UserListItem {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_verified: boolean;
  disabled_at: string | null;
  last_login_at: string | null;
  created_at: string | null;
  roles: string[];
}

interface Role {
  id: string;
  name: string;
}

interface Props {
  user: UserListItem;
  roles: Role[];
  has_permissions_module: boolean;
  auth?: { user?: { id?: string } };
}

function fmt(dt: string | null): string {
  if (!dt) return '—';
  return new Date(dt).toLocaleString();
}

function Edit() {
  const { user, roles, has_permissions_module, auth } = usePage<{ props: Props }>()
    .props as unknown as Props;
  const isSelf = auth?.user?.id === user.id;

  const [isActive, setIsActive] = useState(user.is_active);
  const [isVerified, setIsVerified] = useState(user.is_verified);
  const [selectedRoles, setSelectedRoles] = useState<string[]>(user.roles ?? []);
  const [savingStatus, setSavingStatus] = useState(false);
  const [savingRoles, setSavingRoles] = useState(false);
  const [savingVerify, setSavingVerify] = useState(false);

  const toggleRole = (roleName: string) => {
    setSelectedRoles((prev) =>
      prev.includes(roleName) ? prev.filter((r) => r !== roleName) : [...prev, roleName],
    );
  };

  const post = (url: string, onSuccess: () => void, label: string) => {
    setSavingStatus(true);
    fetch(url, { method: 'PATCH' })
      .then(async (res) => {
        if (res.ok) {
          onSuccess();
          toast.success(label);
        } else {
          toast.error(`Failed to ${label.toLowerCase()}`);
        }
      })
      .catch(() => toast.error('An error occurred'))
      .finally(() => setSavingStatus(false));
  };

  const disableAccount = () =>
    post(`/api/users/admin/${user.id}/disable`, () => setIsActive(false), 'User disabled');
  const enableAccount = () =>
    post(`/api/users/admin/${user.id}/enable`, () => setIsActive(true), 'User enabled');
  const markVerified = () => {
    setSavingVerify(true);
    fetch(`/api/users/admin/${user.id}/verify`, { method: 'PATCH' })
      .then(async (res) => {
        if (res.ok) {
          setIsVerified(true);
          toast.success('User marked verified');
        } else {
          toast.error('Failed to mark verified');
        }
      })
      .catch(() => toast.error('An error occurred'))
      .finally(() => setSavingVerify(false));
  };

  const handleSaveRoles = () => {
    setSavingRoles(true);
    fetch(`/api/users/admin/${user.id}/roles`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role_names: selectedRoles }),
    })
      .then(async (res) => {
        if (res.ok) toast.success('Roles updated');
        else toast.error('Failed to update roles');
      })
      .catch(() => toast.error('An error occurred'))
      .finally(() => setSavingRoles(false));
  };

  const copyResetLink = () => {
    fetch(`/api/users/admin/${user.id}/reset-password-link`, { method: 'POST' })
      .then(async (res) => {
        if (res.ok) {
          const data = await res.json();
          await navigator.clipboard.writeText(data.link ?? data.url ?? '');
          toast.success('Reset link copied to clipboard');
        } else {
          toast.error('Failed to generate reset link');
        }
      })
      .catch(() => toast.error('An error occurred'));
  };

  return (
    <PageShell
      title={user.email}
      description={user.full_name ?? 'Edit user account'}
      actions={
        <Button asChild variant="outline">
          <Link href="/users/admin">Back to Users</Link>
        </Button>
      }
    >
      <div className="grid gap-4 lg:grid-cols-2">
        <DetailsCard user={{ id: user.id, email: user.email, full_name: user.full_name }} />

        <Card className="border-border">
          <CardContent className="pt-5">
            <SectionTitle>Metadata</SectionTitle>
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
              <dt className="text-muted-foreground">Created</dt>
              <dd>{fmt(user.created_at)}</dd>
              <dt className="text-muted-foreground">Last login</dt>
              <dd>{user.last_login_at ? fmt(user.last_login_at) : 'Never'}</dd>
              <dt className="text-muted-foreground">Disabled at</dt>
              <dd>{fmt(user.disabled_at)}</dd>
              <dt className="text-muted-foreground">Verified</dt>
              <dd className="flex items-center gap-2">
                {isVerified ? (
                  <Badge
                    variant="outline"
                    className="border-primary-200 bg-primary-50 text-primary-700"
                  >
                    yes
                  </Badge>
                ) : (
                  <>
                    <Badge
                      variant="outline"
                      className="border-amber-200 bg-amber-50 text-amber-700"
                    >
                      no
                    </Badge>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={markVerified}
                      disabled={savingVerify}
                    >
                      {savingVerify ? 'Saving…' : 'Mark verified'}
                    </Button>
                  </>
                )}
              </dd>
            </dl>
          </CardContent>
        </Card>

        <AccountStatusCard
          email={user.email}
          isActive={isActive}
          savingStatus={savingStatus}
          onDisable={disableAccount}
          onEnable={enableAccount}
          onCopyResetLink={copyResetLink}
        />

        <Card className="border-border lg:col-span-2">
          <CardContent className="pt-5">
            <SectionTitle
              right={
                <div className="flex gap-2">
                  <Button size="sm" variant="ghost" onClick={() => router.reload()}>
                    Discard
                  </Button>
                  <Button size="sm" onClick={handleSaveRoles} disabled={savingRoles}>
                    {savingRoles ? 'Saving…' : 'Save roles'}
                  </Button>
                </div>
              }
            >
              Roles
            </SectionTitle>
            <div className="flex flex-wrap gap-1.5">
              {roles.map((role) => {
                const active = selectedRoles.includes(role.name);
                return (
                  <button
                    key={role.id}
                    type="button"
                    onClick={() => toggleRole(role.name)}
                    className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${
                      active
                        ? 'border-primary-200 bg-primary-600/10 text-primary-700'
                        : 'border-border bg-card text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    {role.name}
                  </button>
                );
              })}
            </div>
            {has_permissions_module && (
              <Link
                href={`/permissions/users/${user.id}/edit`}
                className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-primary-700 hover:text-primary-800"
              >
                <ShieldCheck className="size-4" />
                Manage permissions →
              </Link>
            )}
          </CardContent>
        </Card>

        <DangerZone userId={user.id} email={user.email} isSelf={isSelf} />
      </div>
    </PageShell>
  );
}

Edit.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Edit;
