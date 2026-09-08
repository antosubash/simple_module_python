import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@simple-module-py/ui/components/ui/select';
import type React from 'react';
import { DateRangeField } from './DateRangeField';

export const ALL = '__all__';
/** Exported so other panels (the empty-state filter summary) name the same
 * set of actions instead of hand-copying it and risking drift. */
export const ACTIONS = ['created', 'updated', 'deleted', 'soft_deleted'] as const;

/** A filterable entity type: the class name the column stores, shown as the
 * table name an operator recognises. Built server-side from the registry. */
export interface EntityTypeOption {
  value: string;
  label: string;
}

export interface FilterState {
  entityType: string;
  action: string;
  userId: string;
  fromDate: string;
  toDate: string;
}

/** The filters the server actually queried with — not the unapplied form
 * state above. Shared by Browse (which receives it as props) and BrowseEmpty
 * (which summarizes it) so the two can't drift apart field-for-field. */
export interface AppliedFilters {
  entity_type: string | null;
  action: string | null;
  user_id: string | null;
  correlation_id: string | null;
  from_date: string | null;
  to_date: string | null;
}

interface FilterBarProps {
  state: FilterState;
  entity_types: EntityTypeOption[];
  onChange: (next: FilterState) => void;
  onSubmit: () => void;
  onClear: () => void;
}

/** Label above the control, per the deck — not beside it, and not a
 * placeholder standing in for one. */
function Field({
  htmlFor,
  label,
  children,
}: {
  htmlFor: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-xs text-muted-foreground">
        {label}
      </label>
      {children}
    </div>
  );
}

export function FilterBar({ state, entity_types, onChange, onSubmit, onClear }: FilterBarProps) {
  const { t } = useT();
  const set = (patch: Partial<FilterState>) => onChange({ ...state, ...patch });

  return (
    <Card className="mb-4 p-4">
      <form
        className="grid items-end gap-3.5 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1fr_1fr_auto]"
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
      >
        <Field htmlFor="audit-entity-type" label={t(keys.audit_log.filters.entity_type_label)}>
          <Select value={state.entityType} onValueChange={(v) => set({ entityType: v })}>
            <SelectTrigger id="audit-entity-type" className="w-full max-lg:min-h-11">
              <SelectValue placeholder={t(keys.audit_log.filters.entity_type_all)} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>{t(keys.audit_log.filters.entity_type_all)}</SelectItem>
              {entity_types.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>

        <Field htmlFor="audit-action" label={t(keys.audit_log.filters.action_label)}>
          <Select value={state.action} onValueChange={(v) => set({ action: v })}>
            <SelectTrigger id="audit-action" className="w-full max-lg:min-h-11">
              <SelectValue placeholder={t(keys.audit_log.filters.action_all)} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>{t(keys.audit_log.filters.action_all)}</SelectItem>
              {ACTIONS.map((a) => (
                <SelectItem key={a} value={a}>
                  {t(keys.audit_log.actions[a])}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>

        <Field htmlFor="audit-user-id" label={t(keys.audit_log.filters.user_label)}>
          <Input
            id="audit-user-id"
            value={state.userId}
            onChange={(e) => set({ userId: e.target.value })}
            placeholder={t(keys.audit_log.filters.user_placeholder)}
            className="max-lg:min-h-11"
          />
        </Field>

        <Field htmlFor="audit-date-range" label={t(keys.audit_log.filters.date_range_label)}>
          <DateRangeField
            id="audit-date-range"
            value={{ from: state.fromDate, to: state.toDate }}
            onChange={(range) => set({ fromDate: range.from, toDate: range.to })}
          />
        </Field>

        <div className="flex gap-2.5 sm:col-span-2 lg:col-span-1">
          <Button type="submit" className="flex-1 max-lg:min-h-11 lg:flex-none">
            {t(keys.audit_log.filters.apply)}
          </Button>
          <Button
            type="button"
            variant="outline"
            className="flex-1 max-lg:min-h-11 lg:flex-none"
            onClick={onClear}
          >
            {t(keys.audit_log.filters.clear)}
          </Button>
        </div>
      </form>
    </Card>
  );
}
