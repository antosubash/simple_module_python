import { Head, Link, router } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { ArrowLeft } from 'lucide-react';
import { type FormEvent, useState } from 'react';
import { LogLevelSelect } from './components/LogLevelSelect';
import { LogTable } from './components/LogTable';
import { VIEW_BASE } from './constants';
import type { LogItem } from './logs';

interface Props {
  logs: LogItem[];
  pagination: { page: number; per_page: number; total: number };
  filters: { q: string; level: string; task_id: string };
}

function Logs({ logs, pagination, filters }: Props) {
  const { t } = useT();
  const [q, setQ] = useState(filters.q);
  const [level, setLevel] = useState(filters.level);
  const [taskId, setTaskId] = useState(filters.task_id);

  function visit(page: number, next = { q, level, task_id: taskId }) {
    const query: Record<string, string | number> = {};
    if (next.q) query.q = next.q;
    if (next.level) query.level = next.level;
    if (next.task_id) query.task_id = next.task_id;
    if (page > 1) query.page = page;
    router.get(`${VIEW_BASE}/logs`, query, { preserveScroll: true, preserveState: true });
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    visit(1);
  }

  return (
    <>
      <Head title={t(keys.background_tasks.logs.title)} />
      <PageShell
        title={t(keys.background_tasks.logs.title)}
        description={t(keys.background_tasks.logs.description)}
        back={VIEW_BASE}
        actions={
          <Button variant="outline" asChild className="max-lg:min-h-11">
            <Link href={VIEW_BASE}>
              <ArrowLeft aria-hidden="true" />
              {t(keys.background_tasks.logs.back_button)}
            </Link>
          </Button>
        }
      >
        <form className="mb-4 flex flex-wrap items-center gap-2" onSubmit={submit}>
          <Input
            className="w-64"
            value={q}
            aria-label={t(keys.background_tasks.logs.search_label)}
            placeholder={t(keys.background_tasks.logs.search_placeholder)}
            onChange={(e) => setQ(e.target.value)}
          />
          <Input
            className="w-64 font-mono"
            value={taskId}
            aria-label={t(keys.background_tasks.logs.task_label)}
            placeholder={t(keys.background_tasks.logs.task_placeholder)}
            onChange={(e) => setTaskId(e.target.value)}
          />
          <div className="w-44">
            <LogLevelSelect value={level} onChange={setLevel} />
          </div>
          <Button type="submit" variant="outline">
            {t(keys.background_tasks.logs.apply)}
          </Button>
        </form>
        <LogTable
          showTask
          logs={logs}
          page={pagination.page}
          perPage={pagination.per_page}
          total={pagination.total}
          onPageChange={(page) => visit(page, filters)}
        />
      </PageShell>
    </>
  );
}

Logs.layout = [AdminLayout];
export default Logs;
