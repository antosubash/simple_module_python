import { keys, useT } from '@simple-module/i18n';
import { AuthenticatedLayout } from '@simple-module/ui/layouts/AuthenticatedLayout';
import type React from 'react';
import { ROUTES } from './routes';

type FieldView = {
  name: string;
  env_var: string;
  value: unknown;
  default: unknown;
  description: string;
  is_secret: boolean;
};

type ModuleView = {
  module_name: string;
  package: string;
  env_prefix: string;
  class_name: string;
  fields: FieldView[];
};

type Props = { modules: ModuleView[] };

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'string') return v === '' ? '""' : v;
  if (typeof v === 'boolean' || typeof v === 'number') return String(v);
  return JSON.stringify(v);
}

function Modules({ modules }: Props) {
  const { t } = useT();
  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{t(keys.settings.modules.title)}</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {t(keys.settings.modules.description)}
          </p>
        </div>
        <a href={ROUTES.browse} className="text-sm text-primary hover:underline">
          {t(keys.settings.modules.back_link)}
        </a>
      </div>

      {modules.length === 0 ? (
        <div className="py-12 text-center">
          <h2 className="text-lg font-medium">{t(keys.settings.modules.empty_title)}</h2>
        </div>
      ) : (
        <div className="space-y-6">
          {modules.map((m) => (
            <section key={m.package} className="rounded border">
              <header className="flex items-baseline justify-between border-b bg-muted/40 px-4 py-3">
                <div>
                  <h2 className="text-lg font-semibold">{m.module_name}</h2>
                  <p className="text-xs text-muted-foreground">
                    {m.class_name}
                    {m.env_prefix ? ` · ${m.env_prefix}*` : ''}
                  </p>
                </div>
                <span className="text-xs font-mono text-muted-foreground">{m.package}</span>
              </header>

              {m.fields.length === 0 ? (
                <p className="px-4 py-6 text-sm text-muted-foreground">
                  {t(keys.settings.modules.no_fields)}
                </p>
              ) : (
                <table className="w-full text-left border-collapse text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="py-2 px-4">{t(keys.settings.modules.table.field)}</th>
                      <th className="py-2 px-4">{t(keys.settings.modules.table.env_var)}</th>
                      <th className="py-2 px-4">{t(keys.settings.modules.table.value)}</th>
                      <th className="py-2 px-4">{t(keys.settings.modules.table.default)}</th>
                      <th className="py-2 px-4">{t(keys.settings.modules.table.description)}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {m.fields.map((f) => (
                      <tr key={f.name} className="border-b last:border-b-0">
                        <td className="py-2 px-4 font-mono text-xs">{f.name}</td>
                        <td className="py-2 px-4 font-mono text-xs text-muted-foreground">
                          {f.env_var}
                        </td>
                        <td className="py-2 px-4 font-mono text-xs">
                          {formatValue(f.value)}
                          {f.is_secret && (
                            <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] uppercase text-amber-900">
                              {t(keys.settings.modules.secret_badge)}
                            </span>
                          )}
                        </td>
                        <td className="py-2 px-4 font-mono text-xs text-muted-foreground">
                          {formatValue(f.default)}
                        </td>
                        <td className="py-2 px-4 text-muted-foreground">{f.description || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

Modules.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Modules;
