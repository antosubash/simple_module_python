import { keys, useT } from '@simple-module-py/i18n';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import type { MigrationRow } from './types';

interface Props {
  migrations: MigrationRow[];
  /** `{generate, apply}` — the shell commands the header links copy. */
  commands: { generate: string; apply: string };
  onCopyCommand: (command: string) => void;
}

/** Enough of an Alembic hash to recognise, per the deck's 48px id column. */
const SHORT_ID = 4;

function LinkAction({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-[12.5px] font-medium text-primary-700 hover:text-primary-800 max-lg:min-h-11"
    >
      {label}
    </button>
  );
}

/**
 * Recent Alembic revisions and whether this database has run them.
 *
 * "Generate" and "Apply pending" copy their commands rather than executing:
 * running Alembic from a web request would let a page load rewrite the schema
 * of the database it is reading from.
 */
export function MigrationsCard({ migrations, commands, onCopyCommand }: Props) {
  const { t } = useT();

  return (
    <Card className="border-border">
      <CardContent className="pt-5">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="text-base font-bold font-[var(--font-display)]">
            {t(keys.dashboard.doctor.recent_migrations)}
          </h2>
          <div className="flex items-center gap-3">
            <LinkAction
              label={t(keys.dashboard.doctor.generate)}
              onClick={() => onCopyCommand(commands.generate)}
            />
            <LinkAction
              label={t(keys.dashboard.doctor.apply_pending)}
              onClick={() => onCopyCommand(commands.apply)}
            />
          </div>
        </div>

        {migrations.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {t(keys.dashboard.doctor.migrations_empty)}
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            {migrations.map((row) => (
              <div key={row.id} className="flex items-center gap-3 text-[13px]">
                <code
                  className="w-12 shrink-0 font-mono text-[12.5px] text-muted-foreground"
                  title={row.id}
                >
                  {row.id.slice(0, SHORT_ID)}
                </code>
                {row.module && (
                  <code className="shrink-0 rounded-full border border-border px-2 py-0.5 font-mono text-[11.5px]">
                    {row.module}
                  </code>
                )}
                <span className="min-w-0 flex-1 truncate">{row.message}</span>
                <span
                  className={`shrink-0 text-[12.5px] ${
                    row.applied ? 'text-primary-700' : 'text-amber-700'
                  }`}
                >
                  {row.applied
                    ? t(keys.dashboard.doctor.applied)
                    : t(keys.dashboard.doctor.pending)}
                </span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
