// Frontend mirror of the retained-log DTOs (background_tasks/contracts/logs.py).

import { apiResult } from '@simple-module-py/ui/lib/api';
import { api } from './api';

export interface LogItem {
  id: string;
  ts: string;
  level: number;
  level_name: string;
  logger: string;
  message: string;
  task_id: string | null;
  job_id: string | null;
  tenant_id: string | null;
  correlation_id: string | null;
}

export interface LogPage {
  items: LogItem[];
  total: number;
  page: number;
  per_page: number;
}

/** Minimum-level choices, lowest first; the empty string means no filter. */
export const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] as const;

export const LOG_LEVEL_ALL = '';

export const LEVEL_ERROR = 40;
export const LEVEL_WARNING = 30;

export function levelClass(level: number): string {
  if (level >= LEVEL_ERROR) return 'text-destructive';
  if (level >= LEVEL_WARNING) return 'text-amber-600 dark:text-amber-400';
  return 'text-muted-foreground';
}

/** One task's log lines, newest first. Throws on a non-2xx so the caller can toast. */
export async function fetchExecutionLogs(
  executionId: string,
  level: string,
  page: number,
): Promise<LogPage> {
  const result = await apiResult(
    api.GET('/api/background_tasks/admin/executions/{execution_id}/logs', {
      params: { path: { execution_id: executionId }, query: { page, level: level || undefined } },
    }),
  );
  if (!result.ok) throw new Error(String(result.status));
  return result.data as LogPage;
}
