import { keys, useT } from '@simple-module-py/i18n';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { useEffect, useMemo, useRef, useState } from 'react';

export interface KnownKey {
  key: string;
  type: string;
  description: string;
  module: string;
}

interface Props {
  value: string;
  onChange: (key: string, type?: string) => void;
  knownKeys: KnownKey[];
  error?: string;
}

const MAX_SUGGESTIONS = 8;

/**
 * Setting key input with suggestions drawn from registered module settings.
 *
 * The field is free text, and a mistyped key produces a row that looks saved
 * and is silently never read — the failure mode gives no feedback at all.
 * Suggestions make the intended key one click away.
 *
 * It stays free text on purpose: a module can read settings this screen has
 * no way to enumerate, so a closed list would block legitimate keys. The
 * warning below is advisory, not a validation error.
 */
export function KeyField({ value, onChange, knownKeys, error }: Props) {
  const { t } = useT();
  const [focused, setFocused] = useState(false);
  // Cleared on unmount so the blur timer cannot fire into a dead component
  // when the admin navigates away within its 150ms window.
  const blurTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (blurTimer.current) clearTimeout(blurTimer.current);
    },
    [],
  );

  const matches = useMemo(() => {
    const needle = value.trim().toLowerCase();
    if (!needle) return knownKeys.slice(0, MAX_SUGGESTIONS);
    return knownKeys.filter((k) => k.key.toLowerCase().includes(needle)).slice(0, MAX_SUGGESTIONS);
  }, [value, knownKeys]);

  const isKnown = knownKeys.some((k) => k.key === value.trim());
  const looksModuleScoped = value.includes('.');

  return (
    <div className="space-y-2 sm:col-span-2">
      <Label className="text-sm font-medium text-muted-foreground">
        {t(keys.settings.form.key_label)}
      </Label>
      <div className="relative">
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => setFocused(true)}
          // Delayed so a click on a suggestion lands before the list unmounts.
          onBlur={() => {
            if (blurTimer.current) clearTimeout(blurTimer.current);
            blurTimer.current = setTimeout(() => setFocused(false), 150);
          }}
          required
          autoComplete="off"
          placeholder={t(keys.settings.form.key_placeholder)}
          className="font-mono"
        />
        {focused && matches.length > 0 && (
          <ul className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-md border border-border bg-popover p-1 shadow-md">
            {matches.map((match) => (
              <li key={match.key}>
                <button
                  type="button"
                  // Selecting a key also sets its declared value type, which
                  // is otherwise a second thing to get right by hand.
                  onMouseDown={() => onChange(match.key, match.type)}
                  className="flex w-full flex-col items-start rounded px-2 py-1.5 text-left hover:bg-accent"
                >
                  <span className="font-mono text-xs">{match.key}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {match.module} · {match.type}
                    {match.description ? ` — ${match.description}` : ''}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {error && <p className="text-xs text-destructive">{error}</p>}
      {!error && value.trim() && !isKnown && looksModuleScoped && (
        <p className="text-xs text-amber-700">{t(keys.settings.form.key_unknown_warning)}</p>
      )}
    </div>
  );
}
