import { Link, router, usePage } from '@inertiajs/react';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { StatCard } from '@simple-module-py/ui/components/StatCard';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module-py/ui/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@simple-module-py/ui/components/ui/tabs';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import {
  ArrowDown,
  ArrowUp,
  Mail,
  Plus,
  Search,
  ShieldCheck,
  UserCheck,
  Users,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { type Filters, IndexFilters } from '../../admin/components/IndexFilters';
import { type RoleItem, RolesTab } from '../../admin/components/RolesTab';
import { type UserListItem, UserRow } from '../../admin/components/UserRow';

interface Pagination {
  page: number;
  per_page: number;
  total: number;
}

interface Aggregates {
  active: number;
  unverified: number;
}

interface Props {
  users: UserListItem[];
  pagination: Pagination;
  aggregates: Aggregates;
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

const HEAD_CLASS = 'text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground';

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
    aggregates,
    query: initialQuery,
    roles,
    filters: serverFilters,
  } = usePage<{ props: Props }>().props as unknown as Props;

  const filters: Filters = useMemo(
    () => ({ ...DEFAULT_FILTERS, ...serverFilters }),
    [serverFilters],
  );
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
    <PageShell
      title="Users"
      description="People with access to this workspace. Invites use the configured mailer."
      actions={
        <div className="flex gap-2">
          <Button asChild className="gap-1.5">
            <Link href="/users/admin/create">
              <Plus className="h-4 w-4" />
              Create user
            </Link>
          </Button>
          <Button asChild variant="outline" className="gap-1.5">
            <Link href="/users/admin/invite">
              <Mail className="h-4 w-4" />
              Invite member
            </Link>
          </Button>
        </div>
      }
    >
      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Members" value={pagination.total} icon={Users} />
        <StatCard label="Active" value={aggregates.active} icon={UserCheck} />
        <StatCard
          label="Pending invites"
          value={aggregates.unverified}
          icon={Mail}
          delta={aggregates.unverified > 0 ? 'review' : 'all set'}
          deltaTone={aggregates.unverified > 0 ? 'warning' : 'success'}
        />
        <StatCard label="Roles" value={roles.length} icon={ShieldCheck} />
      </div>

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
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <div className="relative max-w-sm flex-1 min-w-[240px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
              <Input
                placeholder="Search by name or email…"
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
          </div>

          <Card className="border-border overflow-hidden p-0">
            <Table>
              <TableHeader className="bg-secondary/40">
                <TableRow>
                  <TableHead className={HEAD_CLASS}>
                    <button
                      type="button"
                      className="flex items-center gap-0.5 hover:text-foreground"
                      onClick={() => toggleSort('email')}
                    >
                      Member
                      <SortIcon col="email" filters={filters} />
                    </button>
                  </TableHead>
                  <TableHead className={`${HEAD_CLASS} hidden sm:table-cell`}>Role</TableHead>
                  <TableHead className={`${HEAD_CLASS} hidden sm:table-cell`}>Status</TableHead>
                  <TableHead className={`${HEAD_CLASS} hidden lg:table-cell`}>
                    <button
                      type="button"
                      className="flex items-center gap-0.5 hover:text-foreground"
                      onClick={() => toggleSort('last_login_at')}
                    >
                      Last seen
                      <SortIcon col="last_login_at" filters={filters} />
                    </button>
                  </TableHead>
                  <TableHead className="text-right" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((user) => (
                  <UserRow key={user.id} user={user} />
                ))}
                {users.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} className="h-32 text-center">
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
              <Button
                variant="outline"
                size="sm"
                disabled={pagination.page <= 1}
                onClick={() => navigate({ page: pagination.page - 1 })}
              >
                Previous
              </Button>
              <span className="text-sm text-muted-foreground">
                Page {pagination.page} of {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={pagination.page >= totalPages}
                onClick={() => navigate({ page: pagination.page + 1 })}
              >
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
