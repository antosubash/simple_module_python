import { Head, Link, useForm } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Switch } from '@simple-module-py/ui/components/ui/switch';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import { Check, Package, Search } from 'lucide-react';
import type React from 'react';
import { useMemo, useState } from 'react';
import { toast } from 'sonner';

type Group = { name: string; permissions: string[] };
type Role = { id: string; name: string; description: string | null };

type Props = { role: Role; assigned: string[]; groups: Group[] };

function RoleEdit({ role, assigned, groups }: Props) {
  const { t } = useT();
  const { data, setData, put, processing, isDirty, reset } = useForm<{ permissions: string[] }>({
    permissions: assigned,
  });
  const [q, setQ] = useState('');

  const assignedSet = useMemo(() => new Set(data.permissions), [data.permissions]);
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

  function toggleGroup(group: Group, check: boolean) {
    const next = new Set(data.permissions);
    for (const k of group.permissions) {
      if (check) next.add(k);
      else next.delete(k);
    }
    setData('permissions', Array.from(next));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    put(`/permissions/roles/${role.id}`, {
      preserveScroll: true,
      onSuccess: () => toast.success(t(keys.permissions.toasts.saved)),
      onError: () => toast.error(t(keys.permissions.toasts.save_failed)),
    });
  }

  const pct = totalRegistered === 0 ? 0 : (data.permissions.length / totalRegistered) * 100;

  return (
    <>
      <Head title="Edit Role" />
      <PageShell
        title={t(keys.permissions.edit.title, { role: role.name })}
        description={role.description ?? t(keys.permissions.edit.description)}
        actions={
          <>
            <Button
              type="button"
              variant="outline"
              onClick={() => reset('permissions')}
              disabled={!isDirty}
            >
              {t(keys.permissions.edit.reset_button)}
            </Button>
            <Button
              type="submit"
              form="role-edit-form"
              disabled={processing || !isDirty}
              className="gap-1.5"
            >
              <Check className="h-4 w-4" />
              {t(keys.permissions.edit.submit_button)}
            </Button>
            <Button asChild variant="ghost">
              <Link href="/users/admin">{t(keys.permissions.edit.cancel_link)}</Link>
            </Button>
          </>
        }
      >
        <form id="role-edit-form" onSubmit={handleSubmit} className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative max-w-sm flex-1 min-w-[240px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
              <Input
                placeholder="Filter modules…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                className="pl-9"
              />
            </div>
            <div className="ml-auto flex items-center gap-3 text-sm text-muted-foreground">
              <span>
                <strong className="font-bold tracking-tight font-[var(--font-display)] text-foreground">
                  {data.permissions.length}
                </strong>{' '}
                of {totalRegistered} granted
              </span>
              <div className="h-1.5 w-32 overflow-hidden rounded-full bg-secondary">
                <div
                  className="h-full bg-gradient-to-r from-primary-600 to-primary-800 transition-all"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          </div>

          {filtered.length === 0 ? (
            <Card className="border-border">
              <CardContent className="py-12 text-center text-sm text-muted-foreground">
                {t(keys.permissions.edit.empty)}
              </CardContent>
            </Card>
          ) : (
            <div className="flex flex-col gap-3">
              {filtered.map((group) => {
                const allChecked = group.permissions.every((k) => assignedSet.has(k));
                const granted = group.permissions.filter((k) => assignedSet.has(k)).length;
                const lastRowStart = Math.floor((group.permissions.length - 1) / 2) * 2;
                return (
                  <Card key={group.name} className="border-border overflow-hidden p-0">
                    <div className="flex items-center gap-3 border-b border-border bg-secondary/40 px-4 py-3">
                      <span className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-border bg-card text-muted-foreground">
                        <Package className="h-3.5 w-3.5" aria-hidden="true" />
                      </span>
                      <h3 className="flex-1 font-mono text-sm font-semibold text-foreground">
                        {group.name}
                      </h3>
                      <span className="font-mono text-[11px] text-muted-foreground">
                        {granted}/{group.permissions.length}
                      </span>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => toggleGroup(group, !allChecked)}
                      >
                        {allChecked
                          ? t(keys.permissions.edit.clear_group)
                          : t(keys.permissions.edit.select_all_group)}
                      </Button>
                    </div>
                    <div className="grid sm:grid-cols-2">
                      {group.permissions.map((key, i) => (
                        <label
                          key={key}
                          htmlFor={`perm-${key}`}
                          className={`flex items-center gap-3 px-4 py-3 cursor-pointer ${
                            i % 2 === 0 ? 'sm:border-r sm:border-border' : ''
                          } ${i < lastRowStart ? 'border-b border-border' : ''}`}
                        >
                          <Switch
                            id={`perm-${key}`}
                            checked={assignedSet.has(key)}
                            onCheckedChange={(c) => toggle(key, c === true)}
                          />
                          <code className="rounded bg-secondary px-2 py-0.5 font-mono text-[12px] text-foreground">
                            {key}
                          </code>
                        </label>
                      ))}
                    </div>
                  </Card>
                );
              })}
              <div className="flex items-center justify-end gap-2 text-sm text-muted-foreground">
                <Badge variant="outline" className="border-border bg-secondary">
                  {data.permissions.length} / {totalRegistered}
                </Badge>
                <span>permissions enabled</span>
              </div>
            </div>
          )}
        </form>
      </PageShell>
    </>
  );
}

RoleEdit.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default RoleEdit;
