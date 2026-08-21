import { keys, useT } from '@simple-module-py/i18n';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@simple-module-py/ui/components/ui/select';

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
  const { t } = useT();
  return (
    <div className="flex flex-wrap gap-2">
      <Select
        value={filters.status}
        onValueChange={(v) => onChange({ status: v as Filters['status'] })}
      >
        <SelectTrigger size="sm" className="w-32">
          <SelectValue placeholder={t(keys.users.filters.status_placeholder)} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{t(keys.users.filters.status_all)}</SelectItem>
          <SelectItem value="active">{t(keys.users.filters.status_active)}</SelectItem>
          <SelectItem value="disabled">{t(keys.users.filters.status_disabled)}</SelectItem>
        </SelectContent>
      </Select>

      <Select
        value={filters.role || 'all'}
        onValueChange={(v) => onChange({ role: v === 'all' ? '' : v })}
      >
        <SelectTrigger size="sm" className="w-36">
          <SelectValue placeholder={t(keys.users.filters.role_placeholder)} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{t(keys.users.filters.role_all)}</SelectItem>
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
          <SelectValue placeholder={t(keys.users.filters.verified_placeholder)} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{t(keys.users.filters.verified_all)}</SelectItem>
          <SelectItem value="yes">{t(keys.users.filters.verified_yes)}</SelectItem>
          <SelectItem value="no">{t(keys.users.filters.verified_no)}</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
}
