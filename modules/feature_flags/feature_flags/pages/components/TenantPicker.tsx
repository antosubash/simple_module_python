import { keys, useT } from '@simple-module-py/i18n';
import { SegmentedControl } from '@simple-module-py/ui/components/SegmentedControl';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { useState } from 'react';

interface Props {
  /** Currently-viewed tenant, or null for the system scope. */
  tenantId: string | null;
  /** Tenants that already carry at least one override. */
  tenants: string[];
  onSelect: (tenantId: string | null) => void;
}

const SYSTEM = '__system__';
const CUSTOM = '__custom__';

/**
 * Scope picker for the flags table.
 *
 * A segmented control rather than a dropdown: the scope is the difference
 * between an experiment and an outage, so which one is active has to be
 * readable without opening anything.
 *
 * The list cannot be closed: there is no tenant registry in the framework
 * (ids arrive on auth claims), so the only tenants this app can enumerate are
 * those that already have an override. Creating the *first* override for a
 * tenant therefore still needs a way to name one by hand, which is what the
 * last segment is for.
 */
export function TenantPicker({ tenantId, tenants, onSelect }: Props) {
  const { t } = useT();
  const [custom, setCustom] = useState(false);
  const [draft, setDraft] = useState('');

  // The tenant being viewed may not have overrides yet, so it can be absent
  // from `tenants` — without this it would vanish from its own picker.
  const options = [...new Set(tenantId ? [...tenants, tenantId] : tenants)].sort();

  function handleChange(value: string) {
    if (value === CUSTOM) {
      setCustom(true);
      setDraft('');
      return;
    }
    setCustom(false);
    onSelect(value === SYSTEM ? null : value);
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <SegmentedControl
        value={custom ? CUSTOM : (tenantId ?? SYSTEM)}
        onChange={handleChange}
        options={[
          { value: SYSTEM, label: t(keys.feature_flags.browse.scope_system) },
          ...options.map((tid) => ({ value: tid, label: tid })),
          { value: CUSTOM, label: t(keys.feature_flags.browse.scope_custom) },
        ]}
        aria-label={t(keys.feature_flags.browse.scope_label)}
      />

      {custom && (
        <form
          className="flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            const trimmed = draft.trim();
            if (trimmed) onSelect(trimmed);
          }}
        >
          <Input
            id="tenant_id"
            className="h-8 w-44"
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={t(keys.feature_flags.browse.tenant_id_placeholder)}
            aria-label={t(keys.feature_flags.browse.tenant_id_label)}
          />
          <Button type="submit" size="sm" disabled={!draft.trim()}>
            {t(keys.feature_flags.browse.go)}
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={() => setCustom(false)}>
            {t(keys.feature_flags.browse.cancel)}
          </Button>
        </form>
      )}
    </div>
  );
}
