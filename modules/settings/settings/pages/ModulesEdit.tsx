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
  /** Package -> the names of the health checks its module registered. */
  testable?: Record<string, string[]>;
};

function ModulesEdit({ modules, testable = {} }: Props) {
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
      {/* The page scrolls, not the pane. Pinning the pane to
          `100vh - --app-chrome-h` ignored the footer below it, so the shell
          grew past the viewport and the window scrollbar appeared *beside* the
          pane's own — two scrollbars for one list. A min-height gives the same
          full-viewport look, and the module list sticks under the topbar
          instead of scrolling itself. Below `lg` the two panes stack, so a
          390px screen never scrolls sideways. */}
      <div className="flex flex-col bg-background lg:min-h-[calc(100vh-var(--app-chrome-h))] lg:flex-row">
        <aside className="flex w-full shrink-0 flex-col border-b border-border bg-secondary/40 p-3.5 max-lg:max-h-72 max-lg:overflow-y-auto lg:sticky lg:top-[var(--app-chrome-h)] lg:max-h-[calc(100vh-var(--app-chrome-h))] lg:w-[230px] lg:self-start lg:overflow-y-auto lg:border-b-0 lg:border-r lg:py-5">
          <div className="relative mb-2">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              type="search"
              placeholder={t(keys.settings.modules.search_placeholder)}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="h-9 bg-card pl-9 text-[12.5px]"
            />
          </div>
          <nav className="flex flex-col gap-1 overflow-y-auto">
            {filtered.map((m) => {
              const isActive = m.package === selected;
              const overridden = m.fields.filter((f) => f.db_override).length;
              return (
                <button
                  key={m.package}
                  type="button"
                  onClick={() => setSelected(m.package)}
                  // `shrink-0`: inside a scrolling flex column the buttons
                  // were shrinkable, so a long module list on a phone squashed
                  // every row to a 5px sliver instead of scrolling.
                  className={`flex shrink-0 flex-col gap-0.5 rounded-lg px-3 py-2.5 text-left transition-colors max-lg:min-h-11 ${
                    isActive
                      ? 'bg-primary-600/10 text-primary-700'
                      : 'text-foreground hover:bg-card'
                  }`}
                >
                  <code
                    className={`truncate font-mono text-[13px] ${isActive ? 'font-medium' : ''}`}
                  >
                    {m.package}
                  </code>
                  <span
                    className={`text-[11.5px] ${isActive ? 'opacity-75' : 'text-muted-foreground'}`}
                  >
                    {t(keys.settings.modules.field_count, { count: m.fields.length })}
                    {overridden > 0 && (
                      <>
                        <span aria-hidden="true"> · </span>
                        {t(keys.settings.modules.overridden_count, { count: overridden })}
                      </>
                    )}
                  </span>
                </button>
              );
            })}
          </nav>
          <div className="mt-auto border-t border-border pt-3.5 max-lg:mt-3.5">
            <a
              href={ROUTES.browse}
              className="text-[12.5px] font-medium text-primary-700 hover:text-primary-800"
            >
              {t(keys.settings.modules.browse_free_form_link)}
            </a>
          </div>
        </aside>

        {/* `pb-10` rather than a fade: the fields list ends on a full row with
            breathing room under it, not half a row cut off by the pane edge. */}
        <main className="flex min-w-0 flex-1 flex-col p-4 sm:p-6 lg:px-8 lg:pb-10">
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
            <ModuleForm module={current} checks={testable[current.package] ?? []} />
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
