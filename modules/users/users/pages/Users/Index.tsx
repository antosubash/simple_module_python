import { Link, router, usePage } from '@inertiajs/react';
import { PageShell } from '@simple-module/ui/components/PageShell';
import { Badge } from '@simple-module/ui/components/ui/badge';
import { Button } from '@simple-module/ui/components/ui/button';
import { Card } from '@simple-module/ui/components/ui/card';
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
import { ArrowDown, ArrowUp, Pencil, Plus, Search, ShieldCheck, Users } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { type Filters, IndexFilters } from './IndexFilters';
import { type RoleItem, RolesTab } from './RolesTab';

interface UserListItem {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_verified: boolean;
  last_login_at: string | null;
  created_at: string | null;
  roles: string[];
}

interface Pagination {
  page: number;
  per_page: number;
  total: number;
}

interface Props {
  users: UserListItem[];
  pagination: Pagination;
  query: string;
  roles: RoleItem[];
  filters: Filters;
}

const DEFAULT_FILTERS: Filters = {
  status: 'all',
  role: '',
  verified: 'all',
  sort: 'email',
  order: 'asc',
};

function SortIcon({ col, filters }: { col: Filters['sort']; filters: Filters }) {
  if (filters.sort !== col) return null;
  return filters.order === 'asc' ? (
    <ArrowUp className="inline-block ml-1 size-3" />
  ) : (
    <ArrowDown className="inline-block ml-1 size-3" />
  );
}

function Index() {
  const {
    users,
    pagination,
    query: initialQuery,
    roles,
    filters: serverFilters,
  } = usePage<{ props: Props }>().props as unknown as Props;

  const filters: Filters = { ...DEFAULT_FILTERS, ...serverFilters };
  const [search, setSearch] = useState(initialQuery ?? '');

  const navigate = useCallback(
    (next: Partial<{ page: number; q: string } & Filters>) => {
      const params: Record<string, string> = {};
      const q = next.q ?? search;
      const status = next.status ?? filters.status;
      const role = next.role ?? filters.role;
      const verified = next.verified ?? filters.verified;
      const sort = next.sort ?? filters.sort;
      const order = next.order ?? filters.order;
      const page = next.page ?? 1;
      if (q) params.q = q;
      if (status !== 'all') params.status = status;
      if (role) params.role = role;
      if (verified !== 'all') params.verified = verified;
      if (sort !== 'email') params.sort = sort;
      if (order !== 'asc') params.order = order;
      if (page > 1) params.page = String(page);
      router.get('/users/admin', params, { preserveState: true, preserveScroll: true });
    },
    [search, filters],
  );

  const toggleSort = (col: Filters['sort']) => {
    if (filters.sort === col) {
      navigate({ order: filters.order === 'asc' ? 'desc' : 'asc' });
    } else {
      navigate({ sort: col, order: 'asc' });
    }
  };

  useEffect(() => {
    if (search === (initialQuery ?? '')) return;
    const timeout = setTimeout(() => navigate({ q: search }), 300);
    return () => clearTimeout(timeout);
  }, [search, initialQuery, navigate]);

  const totalPages = Math.ceil(pagination.total / pagination.per_page);

  return (
    <PageShell title="Users & Roles" description="Manage user accounts, roles, and permissions.">
      <Tabs defaultValue="users" className="space-y-4">
        <TabsList>
          <TabsTrigger value="users">
            <Users className="size-4" />
            Users
            <Badge variant="secondary" className="ml-1">
              {pagination.total}
            </Badge>
          </TabsTrigger>
          <TabsTrigger value="roles">
            <ShieldCheck className="size-4" />
            Roles
            <Badge variant="secondary" className="ml-1">
              {roles.length}
            </Badge>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="users">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
            <div className="relative max-w-sm flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
              <Input
                placeholder="Search by email or name…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9"
              />
            </div>
            <IndexFilters
              filters={filters}
              roles={roles.map((r) => r.name)}
              onChange={(next) => navigate(next)}
            />
            <Button asChild>
              <Link href="/users/admin/invite">
                <Plus />
                Invite user
              </Link>
            </Button>
          </div>

          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>
                    <button type="button" className="flex items-center gap-0.5 hover:text-foreground" onClick={() => toggleSort('email')}>
                      Email<SortIcon col="email" filters={filters} />
                    </button>
                  </TableHead>
                  <TableHead className="hidden md:table-cell">Name</TableHead>
                  <TableHead className="hidden sm:table-cell">Roles</TableHead>
                  <TableHead className="hidden sm:table-cell">Status</TableHead>
                  <TableHead className="hidden lg:table-cell">
                    <button type="button" className="flex items-center gap-0.5 hover:text-foreground" onClick={() => toggleSort('last_login_at')}>
                      Last login<SortIcon col="last_login_at" filters={filters} />
                    </button>
                  </TableHead>
                  <TableHead className="hidden lg:table-cell">
                    <button type="button" className="flex items-center gap-0.5 hover:text-foreground" onClick={() => toggleSort('created_at')}>
                      Created<SortIcon col="created_at" filters={filters} />
                    </button>
                  </TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((user) => (
                  <TableRow key={user.id}>
                    <TableCell>
                      <div>
                        <span className="font-medium">{user.email}</span>
                        {!user.is_verified && (
                          <Badge variant="outline" className="ml-2 text-xs">unverified</Badge>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="hidden md:table-cell text-muted-foreground text-sm">
                      {user.full_name || '—'}
                    </TableCell>
                    <TableCell className="hidden sm:table-cell">
                      <div className="flex flex-wrap gap-1">
                        {user.roles.length > 0
                          ? user.roles.map((r) => <Badge key={r} variant="secondary">{r}</Badge>)
                          : <span className="text-muted-foreground text-sm">—</span>}
                      </div>
                    </TableCell>
                    <TableCell className="hidden sm:table-cell">
                      <Badge variant={user.is_active ? 'secondary' : 'destructive'}>
                        {user.is_active ? 'Active' : 'Disabled'}
                      </Badge>
                    </TableCell>
                    <TableCell className="hidden lg:table-cell text-sm text-muted-foreground">
                      {user.last_login_at ? new Date(user.last_login_at).toLocaleDateString() : '—'}
                    </TableCell>
                    <TableCell className="hidden lg:table-cell text-sm text-muted-foreground">
                      {user.created_at ? new Date(user.created_at).toLocaleDateString() : '—'}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button asChild variant="ghost" size="icon-sm">
                        <Link href={`/users/admin/${user.id}`}><Pencil /></Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {users.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7} className="h-32 text-center">
                      <div className="flex flex-col items-center gap-2 text-muted-foreground">
                        <Users className="size-8" />
                        <p>{search ? `No users match "${search}"` : 'No users yet'}</p>
                      </div>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Card>

          {totalPages > 1 && (
            <div className="mt-4 flex items-center justify-center gap-2">
              <Button variant="outline" size="sm" disabled={pagination.page <= 1} onClick={() => navigate({ page: pagination.page - 1 })}>
                Previous
              </Button>
              <span className="text-sm text-muted-foreground">Page {pagination.page} of {totalPages}</span>
              <Button variant="outline" size="sm" disabled={pagination.page >= totalPages} onClick={() => navigate({ page: pagination.page + 1 })}>
                Next
              </Button>
            </div>
          )}
        </TabsContent>

        <RolesTab roles={roles} />
      </Tabs>
    </PageShell>
  );
}

Index.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Index;
