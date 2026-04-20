import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@simple-module/ui/components/ui/select';

export interface Filters {
  status: 'all' | 'active' | 'disabled';
  role: string;
  verified: 'all' | 'yes' | 'no';
  sort: 'email' | 'last_login_at' | 'created_at';
  order: 'asc' | 'desc';
}

interface IndexFiltersProps {
  filters: Filters;
  roles: string[];
  onChange: (next: Partial<Filters>) => void;
}

export function IndexFilters({ filters, roles, onChange }: IndexFiltersProps) {
  return (
    <div className="flex flex-wrap gap-2">
      <Select
        value={filters.status}
        onValueChange={(v) => onChange({ status: v as Filters['status'] })}
      >
        <SelectTrigger size="sm" className="w-32">
          <SelectValue placeholder="Status" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All statuses</SelectItem>
          <SelectItem value="active">Active</SelectItem>
          <SelectItem value="disabled">Disabled</SelectItem>
        </SelectContent>
      </Select>

      <Select
        value={filters.role || 'all'}
        onValueChange={(v) => onChange({ role: v === 'all' ? '' : v })}
      >
        <SelectTrigger size="sm" className="w-36">
          <SelectValue placeholder="Role" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All roles</SelectItem>
          {roles.map((r) => (
            <SelectItem key={r} value={r}>
              {r}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={filters.verified}
        onValueChange={(v) => onChange({ verified: v as Filters['verified'] })}
      >
        <SelectTrigger size="sm" className="w-32">
          <SelectValue placeholder="Verified" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All</SelectItem>
          <SelectItem value="yes">Verified</SelectItem>
          <SelectItem value="no">Unverified</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
}
