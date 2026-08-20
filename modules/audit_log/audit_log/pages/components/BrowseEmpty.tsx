import { keys, useT } from '@simple-module-py/i18n';
import { EmptyState } from '@simple-module-py/ui/components/EmptyState';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { ScrollText, SearchX } from 'lucide-react';
import { ACTIONS } from './FilterBar';

/** The filters the server actually queried with — not the unapplied form state. */
export interface AppliedFilters {
  entity_type: string | null;
  action: string | null;
  user_id: string | null;
  correlation_id: string | null;
  from_date: string | null;
  to_date: string | null;
}

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

interface BrowseEmptyProps {
  applied: AppliedFilters;
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
export function BrowseEmpty({ applied, onClear }: BrowseEmptyProps) {
  const { t } = useT();

  if (!hasActiveFilters(applied)) {
    return (
      <Card className="border-border">
        <EmptyState
          className="py-12"
          icon={ScrollText}
          title={t(keys.audit_log.browse.empty_title)}
          description={t(keys.audit_log.browse.empty_description)}
        />
      </Card>
    );
  }

  const parts = [
    applied.entity_type && `${t(keys.audit_log.filters.entity_type_label)}: ${applied.entity_type}`,
    applied.action &&
      `${t(keys.audit_log.filters.action_label)}: ${actionLabel(t, applied.action)}`,
    applied.user_id && `${t(keys.audit_log.filters.user_label)}: ${applied.user_id}`,
    applied.correlation_id &&
      `${t(keys.audit_log.correlation.view_related)}: ${applied.correlation_id}`,
    applied.from_date && `${t(keys.audit_log.filters.from_date_label)}: ${applied.from_date}`,
    applied.to_date && `${t(keys.audit_log.filters.to_date_label)}: ${applied.to_date}`,
  ].filter(Boolean);

  return (
    <Card className="border-border">
      <EmptyState
        className="py-12"
        icon={SearchX}
        title={t(keys.audit_log.browse.no_match_title)}
        description={parts.join(' · ') || t(keys.audit_log.browse.no_match_description)}
        action={
          <Button variant="outline" onClick={onClear}>
            {t(keys.audit_log.browse.clear_filters)}
          </Button>
        }
      />
    </Card>
  );
}
