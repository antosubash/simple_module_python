import { keys, useT } from '@simple-module/i18n';
import { AuthenticatedLayout } from '@simple-module/ui/layouts/AuthenticatedLayout';
import type React from 'react';
import { useMemo, useState } from 'react';
import { ModuleForm, type ModuleView } from './components/ModuleForm';
import { ROUTES } from './routes';

type Props = { modules: ModuleView[] };

function ModulesEdit({ modules }: Props) {
  const { t } = useT();
  const [selected, setSelected] = useState(modules[0]?.package);
  const [q, setQ] = useState('');

  const filtered = useMemo(() => {
    if (!q) return modules;
    const query = q.toLowerCase();
    return modules.filter(
      (m) =>
        m.module_name.toLowerCase().includes(query) ||
        m.package.toLowerCase().includes(query) ||
        m.fields.some((f) => f.name.toLowerCase().includes(query)),
    );
  }, [modules, q]);

  const current = modules.find((m) => m.package === selected);

  return (
    <div className="flex h-[calc(100vh-64px)]">
      <aside className="w-64 border-r bg-muted/40 p-3 overflow-y-auto">
        <input
          type="text"
          placeholder={t(keys.settings.modules.search_placeholder)}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="mb-3 w-full rounded border px-2 py-1 text-sm"
        />
        <nav className="space-y-1">
          {filtered.map((m) => (
            <button
              key={m.package}
              type="button"
              onClick={() => setSelected(m.package)}
              className={`block w-full rounded px-3 py-2 text-left text-sm ${
                m.package === selected ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'
              }`}
            >
              <div className="font-medium">{m.module_name}</div>
              <div className="text-xs opacity-70">
                {m.fields.length} {t(keys.settings.modules.field_count_suffix)}
              </div>
            </button>
          ))}
        </nav>
        <div className="mt-4 border-t pt-3 text-xs">
          <a href={ROUTES.browse} className="text-primary hover:underline">
            {t(keys.settings.modules.browse_free_form_link)}
          </a>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto p-6">
        {current ? (
          <ModuleForm module={current} />
        ) : (
          <p className="text-muted-foreground">{t(keys.settings.modules.empty_title)}</p>
        )}
      </main>
    </div>
  );
}

ModulesEdit.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default ModulesEdit;
