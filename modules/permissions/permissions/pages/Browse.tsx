import { Head, Link, router } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { useState } from 'react';

type Role = { id: string; name: string; label: string; description: string | null; count: number };
type User = { id: string; email: string; full_name: string | null; count: number };
type Props = { roles: Role[]; users: User[]; query: string; roles_editable: boolean };

function Browse({ roles, users, query, roles_editable: rolesEditable }: Props) {
  const { t } = useT();
  const [search, setSearch] = useState(query);
  return (
    <>
      <Head title={t(keys.permissions.browse.title)} />
      <PageShell
        title={t(keys.permissions.browse.title)}
        description={t(keys.permissions.browse.description)}
      >
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>{t(keys.permissions.browse.roles_heading)}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {!rolesEditable && (
                <p className="text-sm text-muted-foreground">
                  {t(keys.permissions.browse.external_roles)}
                </p>
              )}
              {roles.length === 0 && <p>{t(keys.permissions.browse.no_roles)}</p>}
              {roles.map((role) => (
                <div key={role.id} className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-medium">{role.label || role.name}</p>
                    {role.description && (
                      <p className="text-sm text-muted-foreground">{role.description}</p>
                    )}
                    <p className="text-sm">
                      {t(keys.permissions.browse.count_label, { count: role.count })}
                    </p>
                  </div>
                  <Button asChild variant="outline">
                    <Link href={`/admin/permissions/roles/${role.id}/edit`}>
                      {t(keys.permissions.browse.edit_link)}
                    </Link>
                  </Button>
                </div>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>{t(keys.permissions.browse.users_heading)}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  router.get('/admin/permissions/', { q: search }, { preserveState: true });
                }}
              >
                <Input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  aria-label={t(keys.permissions.browse.search_placeholder)}
                  placeholder={t(keys.permissions.browse.search_placeholder)}
                />
              </form>
              {users.length === 0 && <p>{t(keys.permissions.browse.no_users)}</p>}
              {users.map((user) => (
                <div key={user.id} className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-medium">{user.full_name || user.email}</p>
                    <p className="text-sm">
                      {t(keys.permissions.browse.direct_count_label, { count: user.count })}
                    </p>
                  </div>
                  <Button asChild variant="outline">
                    <Link href={`/admin/permissions/users/${user.id}/edit`}>
                      {t(keys.permissions.browse.edit_link)}
                    </Link>
                  </Button>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </PageShell>
    </>
  );
}

Browse.layout = [AdminLayout];
export default Browse;
