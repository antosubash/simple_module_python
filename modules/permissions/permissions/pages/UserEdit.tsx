import { Head, Link, useForm } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { StatCard } from '@simple-module-py/ui/components/StatCard';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import { Check, KeyRound, Link2, Package, Search, ShieldCheck } from 'lucide-react';
import type React from 'react';
import { useMemo, useState } from 'react';
import { toast } from 'sonner';
import { PermissionRow } from './components/PermissionRow';

type Group = { name: string; permissions: string[] };
type UserProp = { id: string; email: string; full_name: string | null };

type Props = {
  user: UserProp;
  roles: string[];
  direct: string[];
  inherited: string[];
  /** Permission key -> roles granting it, so a row can name its source. */
  inherited_by: Record<string, string[]>;
  groups: Group[];
};

function UserEdit({ user, roles, direct, inherited, inherited_by: inheritedBy, groups }: Props) {
  const { t } = useT();
  const { data, setData, put, processing, isDirty, reset } = useForm<{ permissions: string[] }>({
    permissions: direct,
  });
  const [q, setQ] = useState('');

  const directSet = useMemo(() => new Set(data.permissions), [data.permissions]);
  const effectiveSet = useMemo(
    () => new Set([...data.permissions, ...inherited]),
    [data.permissions, inherited],
  );
  const totalRegistered = useMemo(
    () => groups.reduce((sum, g) => sum + g.permissions.length, 0),
    [groups],
  );
  const filtered = useMemo(() => {
    if (!q) return groups;
    const needle = q.toLowerCase();
    return groups.filter((g) => g.name.toLowerCase().includes(needle));
  }, [groups, q]);

  function toggle(key: string, checked: boolean) {
    const next = new Set(data.permissions);
    if (checked) next.add(key);
    else next.delete(key);
    setData('permissions', Array.from(next));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    put(`/permissions/users/${user.id}`, {
      preserveScroll: true,
      onSuccess: () => toast.success(t(keys.permissions.toasts.saved)),
      onError: () => toast.error(t(keys.permissions.toasts.save_failed)),
    });
  }

  return (
    <>
      <Head title="Edit User" />
      <PageShell
        title={t(keys.permissions.user_edit.title, { email: user.email })}
        description={user.full_name || t(keys.permissions.user_edit.description)}
        actions={
          <>
            <Button asChild variant="ghost">
              <Link href="/users/admin">{t(keys.permissions.user_edit.cancel_link)}</Link>
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => reset('permissions')}
              disabled={!isDirty}
            >
              {t(keys.permissions.user_edit.reset_button)}
            </Button>
            <Button
              type="submit"
              form="user-edit-form"
              disabled={processing || !isDirty}
              className="gap-1.5"
            >
              <Check className="h-4 w-4" />
              {t(keys.permissions.user_edit.submit_button)}
            </Button>
          </>
        }
      >
        <form id="user-edit-form" onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Card className="border-border">
              <CardContent className="pt-5">
                <div className="flex items-start justify-between">
                  <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-primary-600/10 text-primary-700">
                    <ShieldCheck className="h-[18px] w-[18px]" aria-hidden="true" />
                  </span>
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {roles.length === 0 ? (
                    <span className="text-sm text-muted-foreground">
                      {t(keys.permissions.user_edit.no_roles)}
                    </span>
                  ) : (
                    roles.map((r) => (
                      <Badge
                        key={r}
                        variant="outline"
                        className="border-primary-200 bg-primary-50 text-primary-700"
                      >
                        {r}
                      </Badge>
                    ))
                  )}
                </div>
                <div className="mt-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                  {t(keys.permissions.user_edit.roles_label)}
                </div>
              </CardContent>
            </Card>
            <StatCard
              label={t(keys.permissions.user_edit.direct_summary)}
              value={data.permissions.length}
              icon={KeyRound}
            />
            <StatCard
              label={t(keys.permissions.user_edit.effective_summary)}
              value={`${effectiveSet.size} / ${totalRegistered}`}
              icon={Link2}
            />
          </div>

          <div className="relative max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
            <Input
              placeholder="Filter modules…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="pl-9"
            />
          </div>

          {filtered.length === 0 ? (
            <Card className="border-border">
              <CardContent className="py-12 text-center text-sm text-muted-foreground">
                {t(keys.permissions.user_edit.empty)}
              </CardContent>
            </Card>
          ) : (
            <div className="flex flex-col gap-3">
              {filtered.map((group) => {
                const granted = group.permissions.filter((k) => effectiveSet.has(k)).length;
                const lastRowStart = Math.floor((group.permissions.length - 1) / 2) * 2;
                return (
                  <Card key={group.name} className="border-border overflow-hidden p-0">
                    <div className="flex items-center gap-3 border-b border-border bg-secondary/40 px-4 py-3">
                      <span className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-primary-600/10 text-primary-700">
                        <Package className="h-3.5 w-3.5" aria-hidden="true" />
                      </span>
                      <h3 className="flex-1 font-mono text-sm font-semibold text-foreground">
                        {group.name}
                      </h3>
                      <span className="font-mono text-[11px] text-muted-foreground">
                        {granted}/{group.permissions.length}
                      </span>
                    </div>
                    <div className="grid sm:grid-cols-2">
                      {group.permissions.map((key, i) => (
                        <PermissionRow
                          key={key}
                          permissionKey={key}
                          direct={directSet.has(key)}
                          viaRoles={inheritedBy[key] ?? []}
                          onToggle={toggle}
                          className={`${i % 2 === 0 ? 'sm:border-r sm:border-border' : ''} ${
                            i < lastRowStart ? 'border-b border-border' : ''
                          }`}
                        />
                      ))}
                    </div>
                  </Card>
                );
              })}
            </div>
          )}
        </form>
      </PageShell>
    </>
  );
}

UserEdit.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default UserEdit;
