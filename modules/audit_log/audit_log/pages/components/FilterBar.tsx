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

export const ALL = '__all__';
/** Exported so other panels (the empty-state filter summary) name the same
 * set of actions instead of hand-copying it and risking drift. */
export const ACTIONS = ['created', 'updated', 'deleted', 'soft_deleted'] as const;

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
  entity_types: string[];
  onChange: (next: FilterState) => void;
  onSubmit: () => void;
  onClear: () => void;
}

export function FilterBar({ state, entity_types, onChange, onSubmit, onClear }: FilterBarProps) {
  const { t } = useT();
  const set = (patch: Partial<FilterState>) => onChange({ ...state, ...patch });

  return (
    <Card className="mb-4 p-4">
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
      >
        <div className="min-w-[140px]">
          <label htmlFor="audit-entity-type" className="block text-sm font-medium mb-1">
            {t(keys.audit_log.filters.entity_type_label)}
          </label>
          <Select value={state.entityType} onValueChange={(v) => set({ entityType: v })}>
            <SelectTrigger id="audit-entity-type" size="sm" className="w-full">
              <SelectValue placeholder={t(keys.audit_log.filters.entity_type_all)} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>{t(keys.audit_log.filters.entity_type_all)}</SelectItem>
              {entity_types.map((et) => (
                <SelectItem key={et} value={et}>
                  {et}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="min-w-[130px]">
          <label htmlFor="audit-action" className="block text-sm font-medium mb-1">
            {t(keys.audit_log.filters.action_label)}
          </label>
          <Select value={state.action} onValueChange={(v) => set({ action: v })}>
            <SelectTrigger id="audit-action" size="sm" className="w-full">
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
        </div>
        <div className="min-w-[160px]">
          <label htmlFor="audit-user-id" className="block text-sm font-medium mb-1">
            {t(keys.audit_log.filters.user_label)}
          </label>
          <Input
            id="audit-user-id"
            value={state.userId}
            onChange={(e) => set({ userId: e.target.value })}
            placeholder={t(keys.audit_log.filters.user_placeholder)}
            className="h-8 text-sm"
          />
        </div>
        <div className="min-w-[140px]">
          <label htmlFor="audit-from-date" className="block text-sm font-medium mb-1">
            {t(keys.audit_log.filters.from_date_label)}
          </label>
          <Input
            id="audit-from-date"
            type="datetime-local"
            value={state.fromDate}
            onChange={(e) => set({ fromDate: e.target.value })}
            className="h-8 text-sm"
          />
        </div>
        <div className="min-w-[140px]">
          <label htmlFor="audit-to-date" className="block text-sm font-medium mb-1">
            {t(keys.audit_log.filters.to_date_label)}
          </label>
          <Input
            id="audit-to-date"
            type="datetime-local"
            value={state.toDate}
            onChange={(e) => set({ toDate: e.target.value })}
            className="h-8 text-sm"
          />
        </div>
        <Button type="submit" size="sm">
          {t(keys.audit_log.filters.apply)}
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onClear}>
          {t(keys.audit_log.filters.clear)}
        </Button>
      </form>
    </Card>
  );
}
