import { Head, Link, router } from '@inertiajs/react';
import { activeLocale, keys, useT } from '@simple-module-py/i18n';
import { ConfirmActionDialog } from '@simple-module-py/ui/components/ConfirmActionDialog';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { useLeaveGuard } from '@simple-module-py/ui/hooks/useLeaveGuard';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { ArrowRight, Box, TriangleAlert } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { ModuleForm, type ModuleView } from '../ui/components/ModuleForm';
import { ModuleNav } from '../ui/components/ModuleNav';
import { settingsText, titleCollator, useLookup } from '../ui/utils/field-text';

type Props = {
  modules: ModuleView[];
  /** Package -> the names of the health checks its module registered. */
  testable?: Record<string, string[]>;
};

function ModulesEdit({ modules, testable = {} }: Props) {
  const { t } = useT();
  // A module with no fields and no page of its own has nothing to show.
  const visible = useMemo(
    () => modules.filter((m) => m.fields.length > 0 || m.manage_url),
    [modules],
  );
  function moduleFromUrl(url: string) {
    const pkg = new URL(url, window.location.origin).searchParams.get('module');
    return visible.find((m) => m.package === pkg)?.package ?? visible[0]?.package;
  }
  const [selected, setSelected] = useState(() => moduleFromUrl(window.location.href));
  const [q, setQ] = useState('');
  const [dirty, setDirty] = useState(false);
  const [pending, setPending] = useState<string>();
  const saving = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const discarded = useRef(false);

  useLeaveGuard(
    dirty,
    t(keys.settings.modules_form.leave_warning),
    saving,
    (visit) =>
      visit.method === 'get' &&
      visit.url.href === window.location.href &&
      visit.preserveState === true &&
      visit.only.length === 1 &&
      visit.only[0] === 'modules',
  );

  useEffect(() => {
    function syncSelection(href: string) {
      const pkg = moduleFromUrl(href);
      setSelected(pkg);
      const url = new URL(href, window.location.origin);
      if (!pkg || !url.searchParams.has('module') || url.searchParams.get('module') === pkg) return;
      url.searchParams.set('module', pkg);
      router.replace({
        url: `${url.pathname}${url.search}${url.hash}`,
        preserveState: true,
        preserveScroll: true,
      });
    }
    syncSelection(window.location.href);
    return router.on('navigate', ({ detail: { page } }) => syncSelection(page.url));
  }, [visible]);

  function select(pkg: string) {
    setDirty(false);
    setSelected(pkg);
    const url = new URL(window.location.href);
    url.searchParams.set('module', pkg);
    router.replace({
      url: `${url.pathname}${url.search}${url.hash}`,
      preserveState: true,
      preserveScroll: true,
    });
  }

  const lookup = useLookup();
  const titles = useMemo(
    () =>
      Object.fromEntries(visible.map((m) => [m.package, settingsText(m.package, lookup).title()])),
    [visible, lookup],
  );
  const locale = activeLocale();
  const collator = useMemo(() => titleCollator(locale), [locale]);
  // Listed by what the reader sees, not by package name.
  const sorted = useMemo(
    () =>
      [...visible].sort((a, b) =>
        collator.compare(titles[a.package] ?? '', titles[b.package] ?? ''),
      ),
    [visible, titles, collator],
  );
  const { filtered, noMatches } = useMemo(() => {
    if (!q) return { filtered: sorted, noMatches: false };
    const query = q.toLowerCase();
    const hit = (s: string) => s.toLowerCase().includes(query);
    const matches = (m: ModuleView) => {
      const text = settingsText(m.package, lookup);
      return (
        hit(titles[m.package] ?? '') ||
        hit(m.package) ||
        m.fields.some((f) => hit(f.name) || hit(text.label(f)))
      );
    };
    // Keep the open module listed even when it doesn't match (#1237), and
    // still say so when nothing does (#1159).
    return {
      filtered: sorted.filter((m) => m.package === selected || matches(m)),
      noMatches: !sorted.some(matches),
    };
  }, [sorted, q, lookup, titles, selected]);

  function pick(pkg: string, from: HTMLElement | null) {
    if (pkg === selected) return;
    if (dirty) {
      returnFocus.current = from;
      discarded.current = false;
      setPending(pkg);
    } else select(pkg);
  }

  const current = visible.find((m) => m.package === selected);

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
        <ModuleNav
          modules={sorted}
          filtered={filtered}
          noMatches={noMatches}
          titles={titles}
          selected={selected}
          query={q}
          onQuery={setQ}
          onPick={pick}
        />

        <div className="flex min-w-0 flex-1 flex-col px-4 pt-5 sm:px-6 lg:px-8 lg:pt-7 lg:pb-8">
          {/* One h1 per screen (#422); the selected module's own heading in
              ModuleForm is an h2 beneath it. */}
          <h1
            ref={heading}
            tabIndex={-1}
            className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground"
          >
            {t(keys.settings.modules.title)}
          </h1>
          {current?.manage_url ? (
            <Card className="border-border p-8">
              {/* No second editor for these fields — the module's own page is
                  the one place they're edited. */}
              <div className="flex max-w-xl flex-col items-start gap-3">
                <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-primary-600/10 text-primary-text">
                  <Box className="h-5 w-5" aria-hidden="true" />
                </span>
                <h2 className="text-lg font-semibold text-foreground">
                  {t(keys.settings.modules.managed_title)}
                </h2>
                <p className="text-sm text-muted-foreground">
                  {t(keys.settings.modules.managed_description, {
                    module: titles[current.package],
                  })}
                </p>
                <Button asChild className="mt-2">
                  <Link href={current.manage_url}>
                    {t(keys.settings.modules.managed_open, { module: titles[current.package] })}
                    <ArrowRight className="ml-1.5 h-4 w-4" aria-hidden="true" />
                  </Link>
                </Button>
              </div>
            </Card>
          ) : current ? (
            <ModuleForm
              key={current.package}
              module={current}
              checks={testable[current.package] ?? []}
              onDirtyChange={setDirty}
            />
          ) : (
            <p className="text-muted-foreground">{t(keys.settings.modules.empty_title)}</p>
          )}
        </div>
      </div>
      <ConfirmActionDialog
        open={pending !== undefined}
        onOpenChange={(open) => {
          if (!open) setPending(undefined);
        }}
        icon={TriangleAlert}
        title={t(keys.settings.modules_form.discard_title)}
        description={t(keys.settings.modules_form.leave_warning)}
        confirmLabel={t(keys.settings.modules_form.discard_changes)}
        cancelLabel={t(keys.settings.form.cancel_button)}
        onConfirm={() => {
          if (pending) {
            discarded.current = true;
            select(pending);
          }
        }}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          (discarded.current ? heading.current : returnFocus.current)?.focus();
        }}
      />
    </>
  );
}

ModulesEdit.layout = [AdminLayout];
export default ModulesEdit;
