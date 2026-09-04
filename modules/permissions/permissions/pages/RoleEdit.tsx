import { Head, Link, useForm } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { USERS_ADMIN_PATH } from '@simple-module-py/ui/lib/auth-routes';
import { Search } from 'lucide-react';
import type React from 'react';
import { useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import { filterGroups, type PermissionGroup } from './components/permission-groups';
import { RoleGroupCard } from './components/RoleGroupCard';
import { useLeaveGuard } from './components/useLeaveGuard';

type Role = { id: string; name: string; description: string | null };

type Props = { role: Role; assigned: string[]; groups: PermissionGroup[] };

/** Grant permissions to a role — every holder of the role gets what is on. */
function RoleEdit({ role, assigned, groups }: Props) {
  const { t } = useT();
  const { data, setData, put, processing, isDirty, reset } = useForm<{ permissions: string[] }>({
    permissions: assigned,
  });
  const [q, setQ] = useState('');
  const [grantedOnly, setGrantedOnly] = useState(false);
  // Set while this page drives its own save visit, so the leave guard does not
  // prompt about changes that are on their way to the server.
  const savingRef = useRef(false);

  const assignedSet = useMemo(() => new Set(data.permissions), [data.permissions]);
  const totalRegistered = useMemo(
    () => groups.reduce((sum, group) => sum + group.permissions.length, 0),
    [groups],
  );
  const visible = useMemo(
    () =>
      filterGroups(groups, q, {
        matchKeys: true,
        keepKey: grantedOnly ? (key) => assignedSet.has(key) : undefined,
      }),
    [groups, q, grantedOnly, assignedSet],
  );

  useLeaveGuard(isDirty, t(keys.permissions.edit.leave_warning), savingRef);

  function toggle(key: string, checked: boolean) {
    const next = new Set(data.permissions);
    if (checked) next.add(key);
    else next.delete(key);
    setData('permissions', Array.from(next));
  }

  function toggleGroup(group: PermissionGroup, check: boolean) {
    const next = new Set(data.permissions);
    for (const key of group.permissions) {
      if (check) next.add(key);
      else next.delete(key);
    }
    setData('permissions', Array.from(next));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    savingRef.current = true;
    put(`/admin/permissions/roles/${role.id}`, {
      preserveScroll: true,
      onSuccess: () => toast.success(t(keys.permissions.toasts.saved)),
      onError: () => toast.error(t(keys.permissions.toasts.save_failed)),
      onFinish: () => {
        savingRef.current = false;
      },
    });
  }

  const pct = totalRegistered === 0 ? 0 : (data.permissions.length / totalRegistered) * 100;

  return (
    <>
      <Head title={t(keys.permissions.edit.head_title)} />
      <PageShell
        title={t(keys.permissions.edit.title, { role: role.name })}
        description={role.description ?? t(keys.permissions.edit.description)}
        // Roles are managed from the Users screen's Roles tab; this path sits
        // outside /users, so the shell is told where the page belongs.
        section={USERS_ADMIN_PATH}
        actions={
          <>
            <Button
              type="button"
              variant="outline"
              className="text-muted-foreground max-lg:min-h-11"
              onClick={() => reset('permissions')}
              disabled={!isDirty}
            >
              {t(keys.permissions.edit.reset_button)}
            </Button>
            <Button asChild variant="outline" className="max-lg:min-h-11">
              <Link href={USERS_ADMIN_PATH}>{t(keys.permissions.edit.cancel_link)}</Link>
            </Button>
            <Button
              type="submit"
              form="role-edit-form"
              className="font-semibold max-lg:min-h-11"
              disabled={processing || !isDirty}
            >
              {t(keys.permissions.edit.submit_button)}
            </Button>
          </>
        }
      >
        <form id="role-edit-form" onSubmit={handleSubmit} className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative min-w-[240px] max-w-[280px] flex-1">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder={t(keys.permissions.edit.filter_placeholder)}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                className="pl-9 max-lg:min-h-11"
              />
            </div>
            <Button
              type="button"
              variant="outline"
              aria-pressed={grantedOnly}
              onClick={() => setGrantedOnly((on) => !on)}
              className={`max-lg:min-h-11 ${
                grantedOnly ? 'border-primary bg-primary-600/10 text-primary-700' : ''
              }`}
            >
              {t(keys.permissions.edit.granted_only)}
            </Button>
            <div className="ml-auto flex items-center gap-3 text-sm text-muted-foreground">
              <span>
                {/* The count carries the emphasis, so it is rendered apart from
                    the sentence rather than interpolated into it. */}
                <b className="font-semibold text-foreground">{data.permissions.length}</b>{' '}
                {t(keys.permissions.edit.granted_summary, { total: totalRegistered })}
              </span>
              <div className="h-1.5 w-32 overflow-hidden rounded-full bg-secondary">
                <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
              </div>
            </div>
          </div>

          {visible.length === 0 ? (
            <Card className="border-border">
              <CardContent className="py-12 text-center text-sm text-muted-foreground">
                {/* An empty registry and an over-narrow filter are different
                    facts; saying the first when the second is true is a lie. */}
                {groups.length === 0
                  ? t(keys.permissions.edit.empty)
                  : t(keys.permissions.edit.no_matches)}
              </CardContent>
            </Card>
          ) : (
            <div className="grid items-start gap-3.5 lg:grid-cols-2">
              {visible.map(({ group, permissions }) => (
                <RoleGroupCard
                  key={group.name}
                  group={group}
                  permissions={permissions}
                  assigned={assignedSet}
                  onToggle={toggle}
                  onToggleGroup={toggleGroup}
                />
              ))}
            </div>
          )}
        </form>
      </PageShell>
    </>
  );
}

RoleEdit.layout = (page: React.ReactNode) => <AdminLayout>{page}</AdminLayout>;
export default RoleEdit;
