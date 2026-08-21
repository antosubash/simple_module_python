import { Link, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module-py/ui/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@simple-module-py/ui/components/ui/tabs';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { ArrowDown, ArrowUp, Plus, Search, ShieldCheck, Users } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { type Filters, IndexFilters } from '../../admin/components/IndexFilters';
import { type RoleItem, RolesTab } from '../../admin/components/RolesTab';
import { type UserListItem, UserRow } from '../../admin/components/UserRow';
import { SoloAccountPrompt, UsersEmptyRow } from '../../admin/components/UsersEmpty';
import { UserStats } from './components/UserStats';

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

/** Member, Role, Status, Last seen, row actions — the empty row spans all of them. */
const COLUMN_COUNT = 5;

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
  const { t } = useT();

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
      router.get('/admin/users/', params, { preserveState: true, preserveScroll: true });
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

  // Sort column and direction are deliberately excluded: reordering an empty
  // list leaves it empty for the same reason it already was, so counting them
  // here would turn "no users yet" into a misleading "no matches".
  const isFiltered =
    !!search ||
    filters.status !== DEFAULT_FILTERS.status ||
    filters.role !== DEFAULT_FILTERS.role ||
    filters.verified !== DEFAULT_FILTERS.verified;

  const clearFilters = useCallback(() => {
    setSearch('');
    navigate({
      q: '',
      status: DEFAULT_FILTERS.status,
      role: DEFAULT_FILTERS.role,
      verified: DEFAULT_FILTERS.verified,
    });
  }, [navigate]);

  return (
    <PageShell
      title={t(keys.users.index.title)}
      description={t(keys.users.index.description)}
      actions={
        // One entry point: invite-vs-create is a choice inside the form, not
        // a choice between two buttons made before seeing either.
        <Button asChild className="gap-1.5">
          <Link href="/admin/users/add">
            <Plus className="h-4 w-4" />
            {t(keys.users.index.add_people)}
          </Link>
        </Button>
      }
    >
      <UserStats
        total={pagination.total}
        active={aggregates.active}
        unverified={aggregates.unverified}
        roleCount={roles.length}
      />

      <Tabs defaultValue="users" className="space-y-4">
        <TabsList>
          <TabsTrigger value="users">
            <Users className="size-4" />
            {t(keys.users.index.tab_users)}
            <Badge variant="secondary" className="ml-1">
              {pagination.total}
            </Badge>
          </TabsTrigger>
          <TabsTrigger value="roles">
            <ShieldCheck className="size-4" />
            {t(keys.users.index.tab_roles)}
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
                placeholder={t(keys.users.index.search_placeholder)}
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

          {pagination.total === 1 && !isFiltered && <SoloAccountPrompt />}

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
                      {t(keys.users.index.col_member)}
                      <SortIcon col="email" filters={filters} />
                    </button>
                  </TableHead>
                  <TableHead className={`${HEAD_CLASS} hidden sm:table-cell`}>
                    {t(keys.users.index.col_role)}
                  </TableHead>
                  <TableHead className={`${HEAD_CLASS} hidden sm:table-cell`}>
                    {t(keys.users.index.col_status)}
                  </TableHead>
                  <TableHead className={`${HEAD_CLASS} hidden lg:table-cell`}>
                    <button
                      type="button"
                      className="flex items-center gap-0.5 hover:text-foreground"
                      onClick={() => toggleSort('last_login_at')}
                    >
                      {t(keys.users.index.col_last_seen)}
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
                  <UsersEmptyRow
                    filtered={isFiltered}
                    columnCount={COLUMN_COUNT}
                    onClear={clearFilters}
                  />
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
                {t(keys.users.index.previous)}
              </Button>
              <span className="text-sm text-muted-foreground">
                {t(keys.users.index.page_of, { page: pagination.page, total: totalPages })}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={pagination.page >= totalPages}
                onClick={() => navigate({ page: pagination.page + 1 })}
              >
                {t(keys.users.index.next)}
              </Button>
            </div>
          )}
        </TabsContent>

        <RolesTab roles={roles} />
      </Tabs>
    </PageShell>
  );
}

Index.layout = (page: React.ReactNode) => <AdminLayout>{page}</AdminLayout>;
export default Index;
