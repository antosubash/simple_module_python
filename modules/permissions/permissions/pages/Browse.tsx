import { Link, router } from '@inertiajs/react';
import { keys, useT } from '@simple-module/i18n';
import { PageShell } from '@simple-module/ui/components/PageShell';
import { Badge } from '@simple-module/ui/components/ui/badge';
import { Button } from '@simple-module/ui/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@simple-module/ui/components/ui/card';
import {
  Empty,
  EmptyDescription,
  EmptyMedia,
  EmptyTitle,
} from '@simple-module/ui/components/ui/empty';
import { Input } from '@simple-module/ui/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module/ui/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@simple-module/ui/components/ui/tabs';
import { AuthenticatedLayout } from '@simple-module/ui/layouts/AuthenticatedLayout';
import { KeyRound, Pencil, Search, ShieldCheck, Users as UsersIcon } from 'lucide-react';
import type React from 'react';
import { useEffect, useState } from 'react';

type Group = { name: string; permissions: string[] };
type Role = {
  id: string;
  name: string;
  description: string | null;
  permission_count: number;
};
type User = {
  id: string;
  email: string;
  full_name: string | null;
  permission_count: number;
};

type Props = { groups: Group[]; roles: Role[]; users: User[]; search: string };

function Browse({ groups, roles, users, search: initialSearch }: Props) {
  const { t } = useT();
  const [search, setSearch] = useState(initialSearch || '');

  useEffect(() => {
    if (search === (initialSearch || '')) return;
    const timeout = setTimeout(() => {
      router.get('/permissions', search ? { q: search } : {}, {
        preserveState: true,
        preserveScroll: true,
      });
    }, 300);
    return () => clearTimeout(timeout);
  }, [search, initialSearch]);

  const totalRegistered = groups.reduce((sum, g) => sum + g.permissions.length, 0);

  return (
    <PageShell
      title={t(keys.permissions.browse.title)}
      description={t(keys.permissions.browse.description)}
    >
      <Tabs defaultValue="roles" className="space-y-4">
        <TabsList>
          <TabsTrigger value="roles">
            <ShieldCheck className="size-4" />
            {t(keys.permissions.browse.roles_heading)}
            <Badge variant="secondary" className="ml-1">
              {roles.length}
            </Badge>
          </TabsTrigger>
          <TabsTrigger value="users">
            <UsersIcon className="size-4" />
            {t(keys.permissions.browse.users_heading)}
            <Badge variant="secondary" className="ml-1">
              {users.length}
            </Badge>
          </TabsTrigger>
          <TabsTrigger value="registry">
            <KeyRound className="size-4" />
            {t(keys.permissions.browse.registry_heading)}
            <Badge variant="secondary" className="ml-1">
              {totalRegistered}
            </Badge>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="roles">
          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="sm:px-6">{t(keys.permissions.table.role)}</TableHead>
                  <TableHead className="hidden md:table-cell sm:px-6">
                    {t(keys.permissions.table.description)}
                  </TableHead>
                  <TableHead className="sm:px-6">{t(keys.permissions.table.assigned)}</TableHead>
                  <TableHead className="text-right sm:px-6">
                    {t(keys.permissions.table.actions)}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {roles.map((role) => (
                  <TableRow key={role.id}>
                    <TableCell className="sm:px-6 font-medium">{role.name}</TableCell>
                    <TableCell className="hidden md:table-cell sm:px-6 text-muted-foreground text-sm">
                      {role.description || '—'}
                    </TableCell>
                    <TableCell className="sm:px-6">
                      <Badge variant="secondary" className="tabular-nums">
                        {role.permission_count}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right sm:px-6">
                      <Button asChild variant="ghost" size="icon-sm">
                        <Link
                          href={`/permissions/roles/${role.id}/edit`}
                          aria-label={t(keys.permissions.browse.edit_link)}
                        >
                          <Pencil />
                        </Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {roles.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4} className="h-40">
                      <Empty>
                        <EmptyMedia variant="icon">
                          <ShieldCheck className="size-5" />
                        </EmptyMedia>
                        <EmptyTitle>{t(keys.permissions.browse.no_roles)}</EmptyTitle>
                      </Empty>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        <TabsContent value="users">
          <div className="mb-4 max-w-sm">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
              <Input
                placeholder={t(keys.permissions.browse.search_placeholder)}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9"
              />
            </div>
          </div>
          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="sm:px-6">{t(keys.permissions.table.user)}</TableHead>
                  <TableHead className="hidden md:table-cell sm:px-6">
                    {t(keys.permissions.table.name)}
                  </TableHead>
                  <TableHead className="sm:px-6">{t(keys.permissions.table.direct)}</TableHead>
                  <TableHead className="text-right sm:px-6">
                    {t(keys.permissions.table.actions)}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((user) => (
                  <TableRow key={user.id}>
                    <TableCell className="sm:px-6 font-medium">{user.email}</TableCell>
                    <TableCell className="hidden md:table-cell sm:px-6 text-muted-foreground text-sm">
                      {user.full_name || '—'}
                    </TableCell>
                    <TableCell className="sm:px-6">
                      <Badge variant="secondary" className="tabular-nums">
                        {user.permission_count}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right sm:px-6">
                      <Button asChild variant="ghost" size="icon-sm">
                        <Link
                          href={`/permissions/users/${user.id}/edit`}
                          aria-label={t(keys.permissions.browse.edit_link)}
                        >
                          <Pencil />
                        </Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {users.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4} className="h-40">
                      <Empty>
                        <EmptyMedia variant="icon">
                          {search ? (
                            <Search className="size-5" />
                          ) : (
                            <UsersIcon className="size-5" />
                          )}
                        </EmptyMedia>
                        <EmptyDescription>{t(keys.permissions.browse.no_users)}</EmptyDescription>
                      </Empty>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        <TabsContent value="registry">
          <p className="text-sm text-muted-foreground mb-4">
            {t(keys.permissions.browse.registry_hint)}
          </p>
          {groups.length === 0 ? (
            <Card>
              <CardContent className="py-12">
                <Empty>
                  <EmptyMedia variant="icon">
                    <KeyRound className="size-5" />
                  </EmptyMedia>
                  <EmptyDescription>{t(keys.permissions.browse.no_permissions)}</EmptyDescription>
                </Empty>
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {groups.map((group) => (
                <Card key={group.name}>
                  <CardHeader>
                    <CardTitle className="flex items-center justify-between text-base">
                      <span>{group.name}</span>
                      <Badge variant="secondary">{group.permissions.length}</Badge>
                    </CardTitle>
                    <CardDescription>
                      {t(keys.permissions.browse.group_description)}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="flex flex-wrap gap-1.5">
                      {group.permissions.map((key) => (
                        <Badge key={key} variant="outline" className="font-mono text-xs">
                          {key}
                        </Badge>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </PageShell>
  );
}

Browse.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Browse;
