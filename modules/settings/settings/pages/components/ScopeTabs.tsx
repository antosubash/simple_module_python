import { keys, useT } from '@simple-module-py/i18n';
import { SegmentedControl } from '@simple-module-py/ui/components/SegmentedControl';

export const SCOPE_FILTERS = ['all', 'system', 'tenant', 'user'] as const;
export type ScopeFilter = (typeof SCOPE_FILTERS)[number];

export type ScopeCounts = Record<ScopeFilter, number>;

interface Props {
  value: ScopeFilter;
  counts: ScopeCounts;
  onChange: (next: ScopeFilter) => void;
}

/**
 * Scope filter for the raw override table, with a tally per tab.
 *
 * The counts come from the server rather than from the rows on screen: the
 * table is paged at 20, so a client-side tally would report "system 20" for a
 * store holding hundreds and get less accurate the more it mattered.
 */
export function ScopeTabs({ value, counts, onChange }: Props) {
  const { t } = useT();

  return (
    <SegmentedControl
      value={value}
      onChange={onChange}
      aria-label={t(keys.settings.browse.scope_filter_label)}
      options={SCOPE_FILTERS.map((scope) => ({
        value: scope,
        label: scope === 'all' ? t(keys.settings.browse.scope_all) : t(keys.settings.scopes[scope]),
        count: counts[scope] ?? 0,
      }))}
    />
  );
}
