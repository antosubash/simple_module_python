import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from '@simple-module-py/ui/components/ui/select';
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
 * This was a free-text box, so viewing a tenant meant knowing and correctly
 * typing its id — and a typo silently showed a scope with no overrides
 * instead of an error.
 *
 * The list cannot be closed: there is no tenant registry in the framework
 * (ids arrive on auth claims), so the only tenants this app can enumerate are
 * those that already have an override. Creating the *first* override for a
 * tenant therefore still needs a way to name one by hand, which is what the
 * "other tenant" branch is for.
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
    <div className="flex flex-wrap items-end gap-3">
      <div className="min-w-[240px]">
        <span className="mb-1 block text-sm font-medium">
          {t(keys.feature_flags.browse.viewing_label)}
        </span>
        <Select value={custom ? CUSTOM : (tenantId ?? SYSTEM)} onValueChange={handleChange}>
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={SYSTEM}>{t(keys.feature_flags.browse.scope_system)}</SelectItem>
            {options.length > 0 && <SelectSeparator />}
            {options.map((tid) => (
              <SelectItem key={tid} value={tid}>
                {tid}
              </SelectItem>
            ))}
            <SelectSeparator />
            <SelectItem value={CUSTOM}>{t(keys.feature_flags.browse.scope_custom)}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {custom && (
        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            const trimmed = draft.trim();
            if (trimmed) onSelect(trimmed);
          }}
        >
          <div className="min-w-[200px]">
            <label className="mb-1 block text-sm font-medium" htmlFor="tenant_id">
              {t(keys.feature_flags.browse.tenant_id_label)}
            </label>
            <Input
              id="tenant_id"
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={t(keys.feature_flags.browse.tenant_id_placeholder)}
            />
          </div>
          <Button type="submit" disabled={!draft.trim()}>
            {t(keys.feature_flags.browse.go)}
          </Button>
          <Button type="button" variant="ghost" onClick={() => setCustom(false)}>
            {t(keys.feature_flags.browse.cancel)}
          </Button>
        </form>
      )}
    </div>
  );
}
