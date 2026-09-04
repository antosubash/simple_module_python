import { Head, Link, useForm } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { StatCard } from '@simple-module-py/ui/components/StatCard';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { USERS_ADMIN_PATH } from '@simple-module-py/ui/lib/auth-routes';
import { Search } from 'lucide-react';
import type React from 'react';
import { useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import { GrantsGroupCard } from './components/GrantsGroupCard';
import { filterGroups, type PermissionGroup } from './components/permission-groups';
import { useLeaveGuard } from './components/useLeaveGuard';

type UserProp = { id: string; email: string; full_name: string | null };

/** Exported so the page's specs are checked against the real prop shape. */
export type Props = {
  user: UserProp;
  roles: string[];
  direct: string[];
  inherited: string[];
  /** Permission key -> roles granting it, so a row can name its source. */
  inherited_by: Record<string, string[]>;
  groups: PermissionGroup[];
};

/** Grant permissions to one user, on top of whatever their roles already give. */
function UserEdit({ user, roles, direct, inherited, inherited_by: inheritedBy, groups }: Props) {
  const { t } = useT();
  const { data, setData, put, processing, isDirty } = useForm<{ permissions: string[] }>({
    permissions: direct,
  });
  const [q, setQ] = useState('');
  // Set while this page drives its own save visit — see `useLeaveGuard`.
  const savingRef = useRef(false);

  const directSet = useMemo(() => new Set(data.permissions), [data.permissions]);
  const effectiveSet = useMemo(
    () => new Set([...data.permissions, ...inherited]),
    [data.permissions, inherited],
  );
  const totalRegistered = useMemo(
    () => groups.reduce((sum, group) => sum + group.permissions.length, 0),
    [groups],
  );
  const visible = useMemo(() => filterGroups(groups, q), [groups, q]);

  useLeaveGuard(isDirty, t(keys.permissions.user_edit.leave_warning), savingRef);

  function toggle(key: string, checked: boolean) {
    const next = new Set(data.permissions);
    if (checked) next.add(key);
    else next.delete(key);
    setData('permissions', Array.from(next));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    savingRef.current = true;
    put(`/admin/permissions/users/${user.id}`, {
      preserveScroll: true,
      onSuccess: () => toast.success(t(keys.permissions.toasts.saved)),
      onError: () => toast.error(t(keys.permissions.toasts.save_failed)),
      onFinish: () => {
        savingRef.current = false;
      },
    });
  }

  return (
    <>
      <Head title={t(keys.permissions.user_edit.head_title)} />
      <PageShell
        title={t(keys.permissions.user_edit.title, { email: user.email })}
        // The name leads the subtitle; without one the sentence stands alone
        // rather than repeating the email already in the title.
        description={
          user.full_name
            ? t(keys.permissions.user_edit.subtitle, { name: user.full_name })
            : t(keys.permissions.user_edit.subtitle_no_name)
        }
        // Reached from the user editor; belongs under Users despite the path.
        section={USERS_ADMIN_PATH}
        actions={
          <>
            <Button asChild variant="outline" className="max-lg:min-h-11">
              <Link href={USERS_ADMIN_PATH}>{t(keys.permissions.user_edit.cancel_link)}</Link>
            </Button>
            <Button
              type="submit"
              form="user-edit-form"
              className="font-semibold max-lg:min-h-11"
              disabled={processing || !isDirty}
            >
              {t(keys.permissions.user_edit.submit_button)}
            </Button>
          </>
        }
      >
        <form id="user-edit-form" onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-3">
            <StatCard
              label={t(keys.permissions.user_edit.roles_label)}
              valueClassName="text-sm font-medium"
              value={
                roles.length === 0 ? (
                  <span className="text-muted-foreground">
                    {t(keys.permissions.user_edit.no_roles)}
                  </span>
                ) : (
                  <span className="flex flex-wrap gap-1.5">
                    {roles.map((role) => (
                      <Badge
                        key={role}
                        variant="outline"
                        className="border-primary bg-primary-600/10 px-2.5 py-0.5 font-medium text-primary-700"
                      >
                        {role}
                      </Badge>
                    ))}
                  </span>
                )
              }
            />
            <StatCard
              label={t(keys.permissions.user_edit.direct_summary)}
              value={data.permissions.length}
            />
            <StatCard
              label={t(keys.permissions.user_edit.effective_summary)}
              value={effectiveSet.size}
              suffix={`/ ${totalRegistered}`}
            />
          </div>

          <div className="flex flex-wrap items-center gap-4">
            <div className="relative min-w-[240px] max-w-[280px] flex-1">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder={t(keys.permissions.filters.modules_placeholder)}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                className="pl-9 max-lg:min-h-11"
              />
            </div>
            <div className="flex items-center gap-4 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <span aria-hidden="true" className="size-2.5 rounded-[3px] bg-primary" />
                {t(keys.permissions.user_edit.legend_direct)}
              </span>
              <span className="flex items-center gap-1.5">
                <span
                  aria-hidden="true"
                  className="size-2.5 rounded-[3px] border border-blue-600 bg-blue-600/25"
                />
                {t(keys.permissions.user_edit.legend_role)}
              </span>
            </div>
          </div>

          {visible.length === 0 ? (
            <Card className="border-border">
              <CardContent className="py-12 text-center text-sm text-muted-foreground">
                {/* See RoleEdit: "nothing registered" and "nothing matched"
                    are different facts and must not share a sentence. */}
                {groups.length === 0
                  ? t(keys.permissions.user_edit.empty)
                  : t(keys.permissions.user_edit.no_matches)}
              </CardContent>
            </Card>
          ) : (
            <div className="grid items-start gap-3.5 lg:grid-cols-2">
              {visible.map(({ group, permissions }) => (
                <GrantsGroupCard
                  key={group.name}
                  group={group}
                  permissions={permissions}
                  direct={directSet}
                  effective={effectiveSet}
                  inheritedBy={inheritedBy}
                  onToggle={toggle}
                />
              ))}
            </div>
          )}
        </form>
      </PageShell>
    </>
  );
}

UserEdit.layout = (page: React.ReactNode) => <AdminLayout>{page}</AdminLayout>;
export default UserEdit;
