import { keys, t } from '@simple-module-py/i18n';
import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { fetchExecutionLogs, LOG_LEVEL_ALL, type LogPage } from '../logs';
import { LogLevelSelect } from './LogLevelSelect';
import { LogTable } from './LogTable';

const EMPTY: LogPage = { items: [], total: 0, page: 1, per_page: 50 };

/** The Logs tab of a task: its retained lines, filtered by minimum level. */
export function LogsPanel({ executionId }: { executionId: string }) {
  const [level, setLevel] = useState(LOG_LEVEL_ALL);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<LogPage>(EMPTY);

  useEffect(() => {
    let live = true;
    fetchExecutionLogs(executionId, level, page)
      .then((next) => live && setData(next))
      .catch(() => live && toast.error(t(keys.background_tasks.logs.load_failed)));
    return () => {
      live = false;
    };
  }, [executionId, level, page]);

  return (
    <div className="space-y-3">
      <div className="max-w-48">
        <LogLevelSelect
          value={level}
          onChange={(next) => {
            setLevel(next);
            setPage(1);
          }}
        />
      </div>
      <LogTable
        logs={data.items}
        page={data.page}
        perPage={data.per_page}
        total={data.total}
        onPageChange={setPage}
      />
    </div>
  );
}
