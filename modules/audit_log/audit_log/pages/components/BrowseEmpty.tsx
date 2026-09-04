import { keys, useT } from '@simple-module-py/i18n';
import { EmptyState } from '@simple-module-py/ui/components/EmptyState';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { ScrollText, SearchX } from 'lucide-react';
import { ACTIONS, type AppliedFilters, type EntityTypeOption } from './FilterBar';
import { formatDateRange } from './format';

export function hasActiveFilters(applied: AppliedFilters): boolean {
  return Object.values(applied).some(Boolean);
}

/**
 * The translated action name, falling back to the raw value for anything
 * unmapped. Checked against FilterBar's own `ACTIONS` list — the same set
 * that drives its dropdown — so a new action added there is translated here
 * too, instead of silently falling back until this file is remembered.
 */
function actionLabel(
  t: (key: (typeof keys.audit_log.actions)[ActionKey]) => string,
  action: string,
): string {
  const known = (ACTIONS as readonly string[]).includes(action);
  return known ? t(keys.audit_log.actions[action as ActionKey]) : action;
}

type ActionKey = (typeof ACTIONS)[number];

/**
 * The table name the dropdown showed, falling back to the stored class name.
 * An unmatched value means the type has since stopped appearing in the log —
 * the filter is still what was applied, so it is still what gets named.
 */
function typeLabel(options: EntityTypeOption[], value: string): string {
  return options.find((option) => option.value === value)?.label ?? value;
}

interface BrowseEmptyProps {
  applied: AppliedFilters;
  /** Same options the filter dropdown offers, so the summary names the type
   * the way the control that set it does. */
  entityTypes: EntityTypeOption[];
  onClear: () => void;
}

/**
 * The audit log's empty panel.
 *
 * A log that has never recorded anything and one whose filters exclude
 * everything look identical, and the difference matters more here than on most
 * screens: "no audit entries" reads as evidence that nothing happened, which
 * is the worst possible thing to tell someone investigating an incident. The
 * filtered case therefore names the filters doing the excluding, so the reader
 * can see it is their query and not the record that is empty.
 */
export function BrowseEmpty({ applied, entityTypes, onClear }: BrowseEmptyProps) {
  const { t } = useT();

  if (!hasActiveFilters(applied)) {
    return (
      <EmptyState
        className="py-12"
        icon={ScrollText}
        title={t(keys.audit_log.browse.empty_title)}
        description={t(keys.audit_log.browse.empty_description)}
      />
    );
  }

  const dateRange = formatDateRange(applied.from_date, applied.to_date);
  const parts = [
    applied.entity_type &&
      `${t(keys.audit_log.filters.entity_type_label)}: ${typeLabel(entityTypes, applied.entity_type)}`,
    applied.action &&
      `${t(keys.audit_log.filters.action_label)}: ${actionLabel(t, applied.action)}`,
    applied.user_id && `${t(keys.audit_log.filters.user_label)}: ${applied.user_id}`,
    applied.correlation_id &&
      `${t(keys.audit_log.correlation.view_related)}: ${applied.correlation_id}`,
    dateRange && `${t(keys.audit_log.filters.date_range_label)}: ${dateRange}`,
  ].filter(Boolean);

  return (
    <EmptyState
      className="py-12"
      icon={SearchX}
      title={t(keys.audit_log.browse.no_match_title)}
      description={parts.join(' · ') || t(keys.audit_log.browse.no_match_description)}
      action={
        <Button variant="outline" className="max-lg:min-h-11" onClick={onClear}>
          {t(keys.audit_log.browse.clear_filters)}
        </Button>
      }
    />
  );
}
