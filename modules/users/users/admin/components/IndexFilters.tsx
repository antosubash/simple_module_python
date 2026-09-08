import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@simple-module-py/ui/components/ui/dropdown-menu';
import { ChevronDown } from 'lucide-react';

export type StatusFilter = 'all' | 'active' | 'unverified' | 'invited' | 'disabled';

export interface Filters {
  status: StatusFilter;
  role: string;
  /** Kept in the URL contract for the JSON API; the UI folds it into Status. */
  verified: 'all' | 'yes' | 'no';
  sort: 'email' | 'last_login_at' | 'created_at';
  order: 'asc' | 'desc';
}

const STATUSES: StatusFilter[] = ['all', 'active', 'unverified', 'invited', 'disabled'];

interface IndexFiltersProps {
  filters: Filters;
  roles: string[];
  onChange: (next: Partial<Filters>) => void;
}

/**
 * Status and Role, as label-prefixed dropdown buttons.
 *
 * "Status: all ▾" says what the control filters *and* what it is currently
 * set to, which a bare "All statuses" select does not — a toolbar of selects
 * makes you open each one to find out whether anything is filtered.
 *
 * The separate Verified select is gone: "verified" was never a third axis, it
 * was two of the five states this one control now offers, and having both let
 * the two disagree ("Status: active" + "Verified: no").
 */
export function IndexFilters({ filters, roles, onChange }: IndexFiltersProps) {
  const { t } = useT();
  const statusLabel: Record<StatusFilter, string> = {
    all: t(keys.users.filters.value_all),
    active: t(keys.users.filters.value_active),
    unverified: t(keys.users.filters.value_unverified),
    invited: t(keys.users.filters.value_invited),
    disabled: t(keys.users.filters.value_disabled),
  };

  return (
    <div className="flex flex-wrap gap-2">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" className="gap-1.5 font-medium max-lg:min-h-11">
            {t(keys.users.filters.status_trigger, { value: statusLabel[filters.status] })}
            <ChevronDown className="size-3.5" aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          {STATUSES.map((value) => (
            <DropdownMenuCheckboxItem
              key={value}
              checked={filters.status === value}
              onSelect={() => onChange({ status: value })}
            >
              {statusLabel[value]}
            </DropdownMenuCheckboxItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" className="gap-1.5 font-medium max-lg:min-h-11">
            {t(keys.users.filters.role_trigger, {
              value: filters.role || t(keys.users.filters.value_all),
            })}
            <ChevronDown className="size-3.5" aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuCheckboxItem
            checked={filters.role === ''}
            onSelect={() => onChange({ role: '' })}
          >
            {t(keys.users.filters.value_all)}
          </DropdownMenuCheckboxItem>
          {roles.map((role) => (
            <DropdownMenuCheckboxItem
              key={role}
              checked={filters.role === role}
              onSelect={() => onChange({ role })}
            >
              {role}
            </DropdownMenuCheckboxItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
