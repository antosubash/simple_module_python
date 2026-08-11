import { Link, router, usePage } from '@inertiajs/react';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { AccountStatusCard } from './components/AccountStatusCard';
import { DangerZone } from './components/DangerZone';
import { DetailsCard } from './components/DetailsCard';
import { MetadataCard } from './components/MetadataCard';
import type { Role } from './components/RolePicker';
import { RolesCard } from './components/RolesCard';

interface UserListItem {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_verified: boolean;
  is_external: boolean;
  disabled_at: string | null;
  last_login_at: string | null;
  created_at: string | null;
  roles: string[];
}

interface Props {
  user: UserListItem;
  roles: Role[];
  has_permissions_module: boolean;
  auth?: { user?: { id?: string } };
}

interface FormState {
  email: string;
  fullName: string;
  roles: string[];
}

function sameRoles(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const sortedB = [...b].sort();
  return [...a].sort().every((role, i) => role === sortedB[i]);
}

/**
 * Edit a user.
 *
 * Details and roles share one dirty state and one Save. They were three
 * independent forms with three save buttons, so a half-finished edit could be
 * abandoned in a way the page never acknowledged, and "did that save?" had
 * three different answers.
 *
 * Status changes (disable/enable, mark verified) stay immediate on purpose.
 * They are actions, not edits: locking out a compromised account should not
 * require finding a Save button, and queuing it behind one would be worse
 * than the inconsistency it removes.
 */
function Edit() {
  const { user, roles, has_permissions_module, auth } = usePage<{ props: Props }>()
    .props as unknown as Props;
  const isSelf = auth?.user?.id === user.id;

  const initial = useMemo<FormState>(
    () => ({
      email: user.email,
      fullName: user.full_name ?? '',
      roles: user.roles ?? [],
    }),
    [user.email, user.full_name, user.roles],
  );

  const [form, setForm] = useState<FormState>(initial);
  const [isActive, setIsActive] = useState(user.is_active);
  const [isVerified, setIsVerified] = useState(user.is_verified);
  const [saving, setSaving] = useState(false);
  const [savingStatus, setSavingStatus] = useState(false);
  const [savingVerify, setSavingVerify] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Re-seed after a server reload, or the form would keep showing pre-save
  // values against a record that has already moved on.
  useEffect(() => {
    setForm(initial);
    setError(null);
  }, [initial]);

  const detailsDirty = form.email !== initial.email || form.fullName !== initial.fullName;
  const rolesDirty = !sameRoles(form.roles, initial.roles);
  const dirty = detailsDirty || rolesDirty;

  // One dirty state is only honest if leaving with unsaved changes is hard to
  // do by accident.
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  const toggleRole = (roleName: string) =>
    setForm((prev) => ({
      ...prev,
      roles: prev.roles.includes(roleName)
        ? prev.roles.filter((r) => r !== roleName)
        : [...prev.roles, roleName],
    }));

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      // Only the parts that changed — sending roles untouched would rewrite
      // every assignment's audit trail for an edit that never touched them.
      if (detailsDirty) {
        const resp = await fetch(`/api/users/admin/${user.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: form.email, full_name: form.fullName || null }),
        });
        if (!resp.ok) {
          const body = await resp.json().catch(() => ({}));
          setError(typeof body?.detail === 'string' ? body.detail : 'Failed to update details');
          return;
        }
      }
      if (rolesDirty) {
        const resp = await fetch(`/api/users/admin/${user.id}/roles`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ role_names: form.roles }),
        });
        if (!resp.ok) {
          setError('Failed to update roles');
          return;
        }
      }
      toast.success('Changes saved');
      router.reload();
    } catch {
      setError('An error occurred');
    } finally {
      setSaving(false);
    }
  }

  const patch = (url: string, onSuccess: () => void, label: string) => {
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
        <div className="flex items-center gap-2">
          {dirty && <span className="text-xs text-muted-foreground">Unsaved changes</span>}
          <Button asChild variant="outline">
            <Link href="/users/admin">Back to Users</Link>
          </Button>
          <Button variant="ghost" onClick={() => setForm(initial)} disabled={!dirty || saving}>
            Discard
          </Button>
          <Button onClick={handleSave} disabled={!dirty || saving}>
            {saving ? 'Saving…' : 'Save changes'}
          </Button>
        </div>
      }
    >
      <div className="grid gap-4 lg:grid-cols-2">
        <DetailsCard
          email={form.email}
          fullName={form.fullName}
          onEmailChange={(email) => setForm((prev) => ({ ...prev, email }))}
          onFullNameChange={(fullName) => setForm((prev) => ({ ...prev, fullName }))}
          error={error}
        />

        <MetadataCard
          isExternal={user.is_external}
          createdAt={user.created_at}
          lastLoginAt={user.last_login_at}
          disabledAt={user.disabled_at}
          isVerified={isVerified}
          savingVerify={savingVerify}
          onMarkVerified={markVerified}
        />

        <AccountStatusCard
          email={user.email}
          isActive={isActive}
          isExternal={user.is_external}
          savingStatus={savingStatus}
          onDisable={() =>
            patch(`/api/users/admin/${user.id}/disable`, () => setIsActive(false), 'User disabled')
          }
          onEnable={() =>
            patch(`/api/users/admin/${user.id}/enable`, () => setIsActive(true), 'User enabled')
          }
          onCopyResetLink={copyResetLink}
        />

        <RolesCard
          roles={roles}
          selected={form.roles}
          onToggle={toggleRole}
          userId={user.id}
          hasPermissionsModule={has_permissions_module}
        />

        <DangerZone userId={user.id} email={user.email} isSelf={isSelf} />
      </div>
    </PageShell>
  );
}

Edit.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Edit;
