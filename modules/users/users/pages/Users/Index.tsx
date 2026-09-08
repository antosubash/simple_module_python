import { Link, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { SegmentedControl } from '@simple-module-py/ui/components/SegmentedControl';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { Plus, Search } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { type Filters, IndexFilters } from '../../admin/components/IndexFilters';
import { type RoleItem, RolesTab } from '../../admin/components/RolesTab';
import { SoloAccountPrompt } from '../../admin/components/UsersEmpty';
import { UsersTable } from '../../admin/components/UsersTable';
import type { UserListItem } from '../../admin/components/user-list-item';
import { UserStats } from './components/UserStats';

interface Pagination {
  page: number;
  per_page: number;
  total: number;
}

interface Aggregates {
  active: number;
  unverified: number;
  invited: number;
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

const ADD_PEOPLE_URL = '/admin/users/add';

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
  const [view, setView] = useState<'users' | 'roles'>('users');

  const navigate = useCallback(
    (next: Partial<{ page: number; q: string } & Filters>) => {
      const params: Record<string, string> = {};
      const q = next.q ?? search;
      const status = next.status ?? filters.status;
      const role = next.role ?? filters.role;
      const sort = next.sort ?? filters.sort;
      const order = next.order ?? filters.order;
      const page = next.page ?? 1;
      if (q) params.q = q;
      if (status !== 'all') params.status = status;
      if (role) params.role = role;
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

  // Sort column and direction are deliberately excluded: reordering an empty
  // list leaves it empty for the same reason it already was, so counting them
  // here would turn "no users yet" into a misleading "no matches".
  const isFiltered =
    !!search || filters.status !== DEFAULT_FILTERS.status || filters.role !== DEFAULT_FILTERS.role;

  const clearFilters = useCallback(() => {
    setSearch('');
    navigate({ q: '', status: DEFAULT_FILTERS.status, role: DEFAULT_FILTERS.role });
  }, [navigate]);

  return (
    <PageShell
      title={t(keys.users.index.title)}
      description={t(keys.users.index.description)}
      mobileAction={{ label: t(keys.users.index.add_people_short), href: ADD_PEOPLE_URL }}
      actions={
        // One entry point: invite-vs-create is a choice inside the form, not
        // a choice between two buttons made before seeing either.
        <Button asChild className="gap-1.5">
          <Link href={ADD_PEOPLE_URL}>
            <Plus className="h-4 w-4" />
            {t(keys.users.index.add_people)}
          </Link>
        </Button>
      }
    >
      <UserStats
        total={pagination.total}
        active={aggregates.active}
        invited={aggregates.invited}
        roleCount={roles.length}
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <SegmentedControl
          value={view}
          onChange={setView}
          aria-label={t(keys.users.index.view_label)}
          options={[
            { value: 'users', label: t(keys.users.index.tab_users), count: pagination.total },
            { value: 'roles', label: t(keys.users.index.tab_roles), count: roles.length },
          ]}
        />
        {view === 'users' && (
          <>
            <div className="relative min-w-60 flex-1">
              <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder={t(keys.users.index.search_placeholder)}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9 max-lg:min-h-11"
              />
            </div>
            <IndexFilters
              filters={filters}
              roles={roles.map((r) => r.name)}
              onChange={(next) => navigate(next)}
            />
          </>
        )}
      </div>

      {view === 'users' ? (
        <>
          {pagination.total === 1 && !isFiltered && <SoloAccountPrompt />}
          <UsersTable
            users={users}
            filters={filters}
            page={pagination.page}
            perPage={pagination.per_page}
            total={pagination.total}
            filtered={isFiltered}
            onSort={toggleSort}
            onPage={(page) => navigate({ page })}
            onClearFilters={clearFilters}
          />
        </>
      ) : (
        <RolesTab roles={roles} />
      )}
    </PageShell>
  );
}

Index.layout = (page: React.ReactNode) => <AdminLayout>{page}</AdminLayout>;
export default Index;
