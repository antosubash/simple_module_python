import { Link, useForm } from '@inertiajs/react';
import { keys, useT } from '@simple-module/i18n';
import { PageShell } from '@simple-module/ui/components/PageShell';
import { Badge } from '@simple-module/ui/components/ui/badge';
import { Button } from '@simple-module/ui/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@simple-module/ui/components/ui/card';
import { Checkbox } from '@simple-module/ui/components/ui/checkbox';
import { Label } from '@simple-module/ui/components/ui/label';
import { AuthenticatedLayout } from '@simple-module/ui/layouts/AuthenticatedLayout';
import { ShieldCheck } from 'lucide-react';
import type React from 'react';
import { toast } from 'sonner';

type Group = { name: string; permissions: string[] };
type Role = { id: string; name: string; description: string | null };

type Props = { role: Role; assigned: string[]; groups: Group[] };

function RoleEdit({ role, assigned, groups }: Props) {
  const { t } = useT();
  const { data, setData, put, processing, isDirty, reset } = useForm<{ permissions: string[] }>({
    permissions: assigned,
  });

  const assignedSet = new Set(data.permissions);
  const totalRegistered = groups.reduce((sum, g) => sum + g.permissions.length, 0);

  function toggle(key: string, checked: boolean) {
    const next = new Set(data.permissions);
    if (checked) next.add(key);
    else next.delete(key);
    setData('permissions', Array.from(next));
  }

  function groupAllSelected(group: Group) {
    return group.permissions.every((k) => assignedSet.has(k));
  }

  function groupSomeSelected(group: Group) {
    return group.permissions.some((k) => assignedSet.has(k));
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

  return (
    <PageShell
      title={t(keys.permissions.edit.title, { role: role.name })}
      description={role.description ?? t(keys.permissions.edit.description)}
      actions={
        <Button asChild variant="outline">
          <Link href="/users/admin">{t(keys.permissions.edit.cancel_link)}</Link>
        </Button>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <Card>
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
            <div className="flex items-center gap-2 text-sm">
              <ShieldCheck className="size-4 text-muted-foreground" />
              <span className="text-muted-foreground">
                {t(keys.permissions.edit.selected_summary)}
              </span>
              <Badge variant="secondary" className="tabular-nums">
                {data.permissions.length} / {totalRegistered}
              </Badge>
            </div>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => reset('permissions')}
                disabled={!isDirty}
              >
                {t(keys.permissions.edit.reset_button)}
              </Button>
              <Button type="submit" disabled={processing || !isDirty}>
                {t(keys.permissions.edit.submit_button)}
              </Button>
            </div>
          </CardContent>
        </Card>

        {groups.length === 0 ? (
          <Card>
            <CardContent className="py-10 text-center text-sm text-muted-foreground">
              {t(keys.permissions.edit.empty)}
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {groups.map((group) => {
              const allChecked = groupAllSelected(group);
              const someChecked = groupSomeSelected(group);
              return (
                <Card key={group.name}>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0">
                    <div>
                      <CardTitle className="text-base">{group.name}</CardTitle>
                      <p className="mt-1 text-xs text-muted-foreground tabular-nums">
                        {group.permissions.filter((k) => assignedSet.has(k)).length} /{' '}
                        {group.permissions.length}
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => toggleGroup(group, !allChecked)}
                    >
                      {allChecked
                        ? t(keys.permissions.edit.clear_group)
                        : someChecked
                          ? t(keys.permissions.edit.select_all_group)
                          : t(keys.permissions.edit.select_all_group)}
                    </Button>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {group.permissions.map((key) => {
                        const id = `perm-${key}`;
                        return (
                          <div key={key} className="flex items-center gap-2.5">
                            <Checkbox
                              id={id}
                              checked={assignedSet.has(key)}
                              onCheckedChange={(c) => toggle(key, c === true)}
                            />
                            <Label
                              htmlFor={id}
                              className="font-mono text-xs font-normal cursor-pointer"
                            >
                              {key}
                            </Label>
                          </div>
                        );
                      })}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </form>
    </PageShell>
  );
}

RoleEdit.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default RoleEdit;
