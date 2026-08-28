import { Head, Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { ArrowRight, Box, Search } from 'lucide-react';
import type React from 'react';
import { useMemo, useState } from 'react';
import { ModuleForm, type ModuleView } from './components/ModuleForm';
import { ROUTES } from './routes';

type Props = {
  modules: ModuleView[];
  /** Packages whose module registered health checks, so "Test connection" applies. */
  testable?: string[];
};

function ModulesEdit({ modules, testable = [] }: Props) {
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
    <>
      <Head title={t(keys.settings.modules.head_title)} />
      {/* Master/detail pane fills the viewport minus the chrome above it,
          whose height the layout publishes as --app-chrome-h. */}
      <div className="flex h-[calc(100vh-var(--app-chrome-h))] bg-background">
        <aside className="w-72 shrink-0 border-r border-border bg-secondary/30 overflow-y-auto">
          <div className="p-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
              <Input
                type="text"
                placeholder={t(keys.settings.modules.search_placeholder)}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                className="pl-9"
              />
            </div>
          </div>
          <nav className="px-2 pb-3 space-y-1">
            {filtered.map((m) => {
              const isActive = m.package === selected;
              return (
                <button
                  key={m.package}
                  type="button"
                  onClick={() => setSelected(m.package)}
                  className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                    isActive
                      ? 'bg-primary-600/10 text-primary-700 font-semibold'
                      : 'text-muted-foreground hover:bg-card hover:text-foreground'
                  }`}
                >
                  <span
                    className={`inline-flex h-7 w-7 items-center justify-center rounded-md ${
                      isActive
                        ? 'bg-primary-600/15 text-primary-700'
                        : 'bg-card text-muted-foreground'
                    }`}
                  >
                    <Box className="h-3.5 w-3.5" aria-hidden="true" />
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="font-mono text-[13px] truncate">{m.module_name}</div>
                    <div className="text-[10px] font-mono opacity-70">
                      {m.fields.length} {t(keys.settings.modules.field_count_suffix)}
                    </div>
                  </div>
                </button>
              );
            })}
          </nav>
          <div className="mx-3 mt-2 border-t border-border pt-3 text-xs">
            <a
              href={ROUTES.browse}
              className="font-semibold text-primary-700 hover:text-primary-800"
            >
              {t(keys.settings.modules.browse_free_form_link)}
            </a>
          </div>
        </aside>

        <main className="flex-1 overflow-y-auto p-6">
          {current?.manage_url ? (
            <Card className="border-border p-8">
              {/* No second editor for these fields — the module's own page is
                  the one place they're edited. */}
              <div className="flex max-w-xl flex-col items-start gap-3">
                <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-primary-600/10 text-primary-700">
                  <Box className="h-5 w-5" aria-hidden="true" />
                </span>
                <h2 className="text-lg font-semibold text-foreground">
                  {t(keys.settings.modules.managed_title)}
                </h2>
                <p className="text-sm text-muted-foreground">
                  {t(keys.settings.modules.managed_description, { module: current.module_name })}
                </p>
                <Button asChild className="mt-2">
                  <Link href={current.manage_url}>
                    {t(keys.settings.modules.managed_open, { module: current.module_name })}
                    <ArrowRight className="ml-1.5 h-4 w-4" aria-hidden="true" />
                  </Link>
                </Button>
              </div>
            </Card>
          ) : current ? (
            <Card className="border-border p-6">
              <ModuleForm module={current} testable={testable.includes(current.package)} />
            </Card>
          ) : (
            <p className="text-muted-foreground">{t(keys.settings.modules.empty_title)}</p>
          )}
        </main>
      </div>
    </>
  );
}

ModulesEdit.layout = (page: React.ReactNode) => <AdminLayout>{page}</AdminLayout>;
export default ModulesEdit;
