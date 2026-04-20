import { Link, useForm } from '@inertiajs/react';
import { keys, useT } from '@simple-module/i18n';
import { PageShell } from '@simple-module/ui/components/PageShell';
import { Badge } from '@simple-module/ui/components/ui/badge';
import { Button } from '@simple-module/ui/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@simple-module/ui/components/ui/card';
import { Checkbox } from '@simple-module/ui/components/ui/checkbox';
import { Label } from '@simple-module/ui/components/ui/label';
import { AuthenticatedLayout } from '@simple-module/ui/layouts/AuthenticatedLayout';
import { Link2, ShieldCheck, User } from 'lucide-react';
import type React from 'react';
import { toast } from 'sonner';

type Group = { name: string; permissions: string[] };
type UserProp = { id: string; email: string; full_name: string | null };

type Props = {
  user: UserProp;
  roles: string[];
  direct: string[];
  inherited: string[];
  groups: Group[];
};

function UserEdit({ user, roles, direct, inherited, groups }: Props) {
  const { t } = useT();
  const inheritedSet = new Set(inherited);
  const { data, setData, put, processing, isDirty, reset } = useForm<{ permissions: string[] }>({
    permissions: direct,
  });

  const directSet = new Set(data.permissions);
  const effectiveSet = new Set([...data.permissions, ...inherited]);
  const totalRegistered = groups.reduce((sum, g) => sum + g.permissions.length, 0);

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
    <PageShell
      title={t(keys.permissions.user_edit.title, { email: user.email })}
      description={user.full_name || t(keys.permissions.user_edit.description)}
      actions={
        <Button asChild variant="outline">
          <Link href="/users/admin">{t(keys.permissions.user_edit.cancel_link)}</Link>
        </Button>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <Card>
          <CardContent className="flex flex-wrap items-center gap-3 py-4">
            <User className="size-4 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">
              {t(keys.permissions.user_edit.roles_label)}
            </span>
            {roles.length === 0 ? (
              <span className="text-sm text-muted-foreground">
                {t(keys.permissions.user_edit.no_roles)}
              </span>
            ) : (
              roles.map((r) => (
                <Badge key={r} variant="secondary">
                  {r}
                </Badge>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
            <div className="flex items-center gap-4 text-sm">
              <div className="flex items-center gap-2">
                <ShieldCheck className="size-4 text-muted-foreground" />
                <span className="text-muted-foreground">
                  {t(keys.permissions.user_edit.direct_summary)}
                </span>
                <Badge variant="secondary" className="tabular-nums">
                  {data.permissions.length}
                </Badge>
              </div>
              <div className="flex items-center gap-2">
                <Link2 className="size-4 text-muted-foreground" />
                <span className="text-muted-foreground">
                  {t(keys.permissions.user_edit.effective_summary)}
                </span>
                <Badge variant="outline" className="tabular-nums">
                  {effectiveSet.size} / {totalRegistered}
                </Badge>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => reset('permissions')}
                disabled={!isDirty}
              >
                {t(keys.permissions.user_edit.reset_button)}
              </Button>
              <Button type="submit" disabled={processing || !isDirty}>
                {t(keys.permissions.user_edit.submit_button)}
              </Button>
            </div>
          </CardContent>
        </Card>

        {groups.length === 0 ? (
          <Card>
            <CardContent className="py-10 text-center text-sm text-muted-foreground">
              {t(keys.permissions.user_edit.empty)}
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {groups.map((group) => (
              <Card key={group.name}>
                <CardHeader>
                  <CardTitle className="text-base flex items-center justify-between">
                    <span>{group.name}</span>
                    <Badge variant="secondary" className="tabular-nums">
                      {group.permissions.filter((k) => effectiveSet.has(k)).length} /{' '}
                      {group.permissions.length}
                    </Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {group.permissions.map((key) => {
                      const fromRole = inheritedSet.has(key);
                      const id = `perm-${key}`;
                      return (
                        <div
                          key={key}
                          className="flex items-center gap-2.5"
                          title={
                            fromRole ? t(keys.permissions.user_edit.inherited_hint) : undefined
                          }
                        >
                          <Checkbox
                            id={id}
                            checked={directSet.has(key)}
                            onCheckedChange={(c) => toggle(key, c === true)}
                          />
                          <Label
                            htmlFor={id}
                            className="font-mono text-xs font-normal cursor-pointer flex items-center gap-2"
                          >
                            <span className={fromRole && !directSet.has(key) ? 'opacity-70' : ''}>
                              {key}
                            </span>
                            {fromRole && (
                              <Badge variant="outline" className="text-[10px] py-0 px-1.5">
                                {t(keys.permissions.user_edit.inherited_badge)}
                              </Badge>
                            )}
                          </Label>
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </form>
    </PageShell>
  );
}

UserEdit.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default UserEdit;
