import { keys, useT } from '@simple-module-py/i18n';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { ValueType } from '../types';

export interface KnownKey {
  key: string;
  type: string;
  /** `SM_<PACKAGE>_<FIELD>` label for this field. */
  env_var: string;
  /** The declaring class reads env at all (it declares an `env_prefix`). */
  env_readable: boolean;
  /** That env var is genuinely read *and* set in this deployment. */
  env_set: boolean;
  /** Its contents, masked for secrets — the fallback, not the live value. */
  env_value: string | null;
  default: unknown;
  requires_restart: boolean;
  is_secret: boolean;
  /** Closed set of accepted values, or null when the field is free text. */
  choices: string[] | null;
}

interface Props {
  value: string;
  onChange: (key: string, type?: string) => void;
  knownKeys: KnownKey[];
  error?: string;
}

const MAX_SUGGESTIONS = 8;

/** The right-hand meta on a suggestion row: what this key resolves to today. */
function SuggestionMeta({ match }: { match: KnownKey }) {
  const { t } = useT();
  const fallback = match.default;
  // The deck's short spelling — "str · env SM_USERS_SMTP_HOST" — in a column
  // that has to fit beside a dotted key. A registry declaration can name a type
  // this catalog has no short form for, so fall back to the raw string.
  const short = keys.settings.value_types_short[match.type as ValueType];
  const type = short ? t(short) : match.type;

  if (match.env_readable && match.env_set) {
    return <>{t(keys.settings.form.suggestion_env, { type, env_var: match.env_var })}</>;
  }
  if (fallback !== null && fallback !== undefined && fallback !== '') {
    return <>{t(keys.settings.form.suggestion_default, { type, default: String(fallback) })}</>;
  }
  // No env fallback and no default worth quoting — the type is the whole story.
  return <>{type}</>;
}

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
    <div className="space-y-1.5">
      <Label className="text-[12.5px] font-medium text-muted-foreground">
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
          <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-md border border-border bg-popover shadow-lg">
            <p className="bg-secondary px-3 py-2 text-[12.5px] text-muted-foreground">
              {t(keys.settings.form.suggestions_header)}
            </p>
            <ul className="max-h-64 overflow-y-auto">
              {matches.map((match) => (
                <li key={match.key}>
                  <button
                    type="button"
                    // Selecting a key also sets its declared value type, which
                    // is otherwise a second thing to get right by hand.
                    onMouseDown={() => onChange(match.key, match.type)}
                    className={`flex w-full items-center justify-between gap-3 border-t border-border px-3 py-2 text-left hover:bg-accent ${
                      match.key === value.trim() ? 'bg-primary-600/10' : ''
                    }`}
                  >
                    <span className="truncate font-mono text-[13px]">{match.key}</span>
                    <span className="shrink-0 text-[11.5px] text-muted-foreground">
                      <SuggestionMeta match={match} />
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {error && <p className="text-xs text-destructive">{error}</p>}
      {!error && value.trim() && !isKnown && looksModuleScoped && (
        <p className="text-xs text-amber-700">{t(keys.settings.form.key_unknown_warning)}</p>
      )}
    </div>
  );
}
