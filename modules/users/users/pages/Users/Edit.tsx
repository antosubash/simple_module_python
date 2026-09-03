import { usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { useRelativeTime } from '@simple-module-py/ui/hooks/use-relative-time';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { initials } from '@simple-module-py/ui/lib/initials';
import type React from 'react';
import { StatusPill } from '../../admin/components/StatusPill';
import { deriveState, type UserListItem } from '../../admin/components/user-list-item';
import { AccountCard } from './components/AccountCard';
import { DangerZone } from './components/DangerZone';
import { DetailsCard } from './components/DetailsCard';
import { EditHeaderActions } from './components/EditHeaderActions';
import { type ActivityEntry, RecentActivityCard } from './components/RecentActivityCard';
import type { Role } from './components/RolePicker';
import { useEditUserForm } from './components/useEditUserForm';
import { useUserActions } from './components/useUserActions';

interface Props {
  user: UserListItem;
  roles: Role[];
  has_permissions_module: boolean;
  /** `null` when the audit_log module is not installed. */
  recent_activity: ActivityEntry[] | null;
  auth?: { user?: { id?: string } };
}

/** "Mar 2026" — when someone joined is a month, never a minute. */
function joinedMonth(value: string | null): string {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '';
  return parsed.toLocaleDateString(undefined, { month: 'short', year: 'numeric' });
}

/**
 * Edit a user.
 *
 * The header carries the identity — avatar, name, address, when they joined,
 * when they were last here, and the status pill — so the cards below are only
 * about what can be changed. Status changes (disable/enable, mark verified)
 * stay immediate on purpose: they are actions, not edits.
 */
function Edit() {
  const {
    user,
    roles,
    has_permissions_module,
    recent_activity: recentActivity,
    auth,
  } = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();
  const { ago } = useRelativeTime();
  const isSelf = auth?.user?.id === user.id;

  const form = useEditUserForm(user);
  const actions = useUserActions(user.id, user.is_active, user.is_verified);

  return (
    <PageShell
      title={user.full_name || user.email}
      back="/admin/users/"
      leading={
        <span className="inline-flex h-13 w-13 shrink-0 items-center justify-center rounded-full bg-primary-600/10 text-lg font-bold text-primary-700 font-[var(--font-display)] dark:text-primary-400">
          {initials(user.full_name, user.email)}
        </span>
      }
      badge={
        <StatusPill state={deriveState(actions.isActive, actions.isVerified, user.invited_at)} />
      }
      description={t(keys.users.edit.subtitle, {
        email: user.email,
        joined: joinedMonth(user.created_at),
        lastLogin: user.last_login_at ? ago(user.last_login_at) : t(keys.users.edit.never),
      })}
      actions={
        <EditHeaderActions
          dirtyCount={form.dirtyCount}
          saving={form.saving}
          onDiscard={form.discard}
          onSave={form.save}
        />
      }
    >
      <div className="grid items-stretch gap-4 lg:grid-cols-[1.3fr_1fr]">
        <DetailsCard
          email={form.form.email}
          fullName={form.form.fullName}
          onEmailChange={(email) => form.setForm((prev) => ({ ...prev, email }))}
          onFullNameChange={(fullName) => form.setForm((prev) => ({ ...prev, fullName }))}
          roles={roles}
          selectedRoles={form.form.roles}
          onToggleRole={form.toggleRole}
          userId={user.id}
          hasPermissionsModule={has_permissions_module}
          error={form.error}
        />

        <AccountCard
          email={user.email}
          isExternal={user.is_external}
          createdAt={user.created_at}
          disabledAt={user.disabled_at ?? null}
          isActive={actions.isActive}
          isVerified={actions.isVerified}
          savingStatus={actions.savingStatus}
          savingVerify={actions.savingVerify}
          onDisable={actions.disable}
          onEnable={actions.enable}
          onMarkVerified={actions.markVerified}
          onCopyResetLink={actions.copyResetLink}
        />

        {/* Absent, not empty, when the deployment records nothing. */}
        {recentActivity !== null && (
          <RecentActivityCard entries={recentActivity} userId={user.id} />
        )}

        <DangerZone userId={user.id} email={user.email} isSelf={isSelf} />
      </div>
    </PageShell>
  );
}

Edit.layout = (page: React.ReactNode) => <AdminLayout>{page}</AdminLayout>;
export default Edit;
