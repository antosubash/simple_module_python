import { keys, useT } from '@simple-module-py/i18n';
import { Input } from '@simple-module-py/ui/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@simple-module-py/ui/components/ui/select';
import { Search } from 'lucide-react';
import { useId, useRef } from 'react';
import { ROUTES } from '../../pages/routes';
import type { ModuleView } from './ModuleForm';

type Props = {
  modules: ModuleView[];
  /** `modules` after the search filter; the rail shows these. */
  filtered: ModuleView[];
  titles: Record<string, string>;
  selected?: string;
  query: string;
  onQuery: (q: string) => void;
  /** `from` is the control to return focus to if a discard prompt is cancelled. */
  onPick: (pkg: string, from: HTMLElement | null) => void;
};

function overriddenCount(m: ModuleView): number {
  return m.fields.filter((f) => f.db_override).length;
}

/**
 * Module navigation. Wide screens get a rail with search; below `lg` a
 * full-width select replaces it — the rail used to stack above the form as a
 * 288px scroll box that pushed every field below the first screen.
 */
export function ModuleNav({ modules, filtered, titles, selected, query, onQuery, onPick }: Props) {
  const { t } = useT();
  const selectId = useId();
  const trigger = useRef<HTMLButtonElement>(null);

  return (
    <>
      <div className="flex flex-col gap-1.5 border-b border-border bg-card px-4 py-3 sm:px-6 lg:hidden">
        <label htmlFor={selectId} className="text-xs font-semibold text-muted-foreground">
          {t(keys.settings.modules.module_picker_label)}
        </label>
        <Select value={selected} onValueChange={(pkg) => onPick(pkg, trigger.current)}>
          <SelectTrigger
            ref={trigger}
            id={selectId}
            className="h-12 w-full text-[15px] font-semibold"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {modules.map((m) => (
              <SelectItem key={m.package} value={m.package} className="min-h-11">
                {titles[m.package]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <a
          href={ROUTES.browse}
          className="self-start py-1 text-[13px] font-medium text-primary-700 dark:text-primary-300 pointer-coarse:min-h-11 pointer-coarse:py-3"
        >
          {t(keys.settings.modules.browse_free_form_link)}
        </a>
      </div>

      <aside className="sticky top-[var(--app-chrome-h)] flex max-h-[calc(100vh-var(--app-chrome-h))] w-[248px] shrink-0 flex-col self-start overflow-y-auto border-r border-border bg-secondary/40 px-3.5 py-5 max-lg:hidden">
        <div className="relative mb-3">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            type="search"
            placeholder={t(keys.settings.modules.search_placeholder)}
            aria-label={t(keys.settings.modules.search_placeholder)}
            value={query}
            onChange={(e) => onQuery(e.target.value)}
            className="h-10 bg-card pl-9 text-[13px]"
          />
        </div>
        <nav
          aria-label={t(keys.settings.modules.navigation_label)}
          className="flex flex-col gap-0.5"
        >
          {filtered.map((m) => {
            const isActive = m.package === selected;
            const overridden = overriddenCount(m);
            return (
              <button
                key={m.package}
                type="button"
                aria-current={isActive ? 'page' : undefined}
                title={m.package}
                onClick={(event) => {
                  if (!isActive) onPick(m.package, event.currentTarget);
                }}
                // `shrink-0`: in a scrolling flex column a long list would
                // otherwise squash every row instead of scrolling.
                className={`flex shrink-0 items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors pointer-coarse:min-h-11 ${
                  isActive
                    ? 'bg-primary-600/10 font-semibold text-primary-700 dark:text-primary-300'
                    : 'text-foreground hover:bg-card'
                }`}
              >
                <span className="min-w-0 truncate">{titles[m.package]}</span>
                <span className="flex shrink-0 items-center gap-1.5 text-xs font-normal text-muted-foreground">
                  {overridden > 0 && (
                    <span
                      className="size-1.5 rounded-full bg-primary-600"
                      role="img"
                      aria-label={t(keys.settings.modules.overridden_count, { count: overridden })}
                    />
                  )}
                  <span aria-hidden="true">{m.fields.length}</span>
                  <span className="sr-only">
                    {t(keys.settings.modules.field_count, { count: m.fields.length })}
                  </span>
                </span>
              </button>
            );
          })}
          {filtered.length === 0 && modules.length > 0 && (
            <p role="status" className="px-3 py-2 text-sm text-muted-foreground">
              {t(keys.settings.modules.no_results)}
            </p>
          )}
        </nav>
        <div className="mt-auto border-t border-border pt-3.5">
          <a
            href={ROUTES.browse}
            className="inline-flex items-center text-[13px] font-medium text-primary-700 hover:text-primary-800 dark:text-primary-300"
          >
            {t(keys.settings.modules.browse_free_form_link)}
          </a>
        </div>
      </aside>
    </>
  );
}
