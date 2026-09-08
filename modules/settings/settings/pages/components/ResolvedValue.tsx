import { keys, useT } from '@simple-module-py/i18n';
import { Card } from '@simple-module-py/ui/components/ui/card';
import type React from 'react';
import type { KnownKey } from './KeyField';

interface Props {
  /** The value being typed into the form right now. */
  draft: string;
  /** The registered key the form currently names, when it names one. */
  known?: KnownKey;
}

function Row({
  label,
  active,
  children,
}: {
  label: string;
  active?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div
      className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 ${
        active ? 'border-primary bg-primary-600/10' : 'border-border opacity-70'
      }`}
    >
      <span
        className={`text-[11.5px] font-medium ${active ? 'text-primary-700' : 'text-muted-foreground'}`}
      >
        {label}
      </span>
      <code
        className={`ml-auto truncate font-mono text-[12.5px] ${active ? '' : 'text-muted-foreground'}`}
      >
        {children}
      </code>
    </div>
  );
}

/**
 * What this key resolves to today, and what the new override will beat.
 *
 * Half the overrides written on this screen restate a value the app already
 * has: the module default is already what someone wants, or an env var is
 * already supplying it. Showing the chain beside the form makes that visible
 * before the row is saved rather than after someone wonders why nothing
 * changed.
 *
 * The env row is honest about modules that never read the environment. The
 * bundled settings classes are DB-backed and declare no `env_prefix`, so their
 * `SM_*` names are labels for the import CLI, not a fallback — calling that an
 * "env fallback" would invert the very question this panel answers.
 */
export function ResolvedValue({ draft, known }: Props) {
  const { t } = useT();

  const envValue = (() => {
    if (!known?.env_readable) return t(keys.settings.resolved.not_read);
    if (!known.env_set) return t(keys.settings.resolved.not_set);
    return known.env_value ?? t(keys.settings.resolved.not_set);
  })();

  const fallback = known?.default;
  const hasDefault = fallback !== null && fallback !== undefined && fallback !== '';

  return (
    <Card className="gap-3.5 border-border p-5">
      <h2 className="font-display text-base font-bold">{t(keys.settings.resolved.title)}</h2>
      <div className="flex flex-col gap-2.5">
        <Row label={t(keys.settings.resolved.this_override)} active>
          {draft || t(keys.settings.resolved.unset)}
        </Row>
        <Row label={t(keys.settings.resolved.env_fallback)}>{envValue}</Row>
        <Row label={t(keys.settings.resolved.module_default)}>
          {/* Deck renders an absent default as an empty pair of quotes; it
              reads as a value rather than as a rendering gap. */}
          {hasDefault ? String(fallback) : '""'}
        </Row>
      </div>
      <p className="text-[12.5px] leading-relaxed text-muted-foreground">
        {known?.requires_restart
          ? t(keys.settings.resolved.restart_note)
          : t(keys.settings.resolved.no_restart_note)}
      </p>
    </Card>
  );
}
