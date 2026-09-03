import { Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { CopyableId } from '@simple-module-py/ui/components/CopyableId';
import { Card } from '@simple-module-py/ui/components/ui/card';
import type { ReactNode } from 'react';
import {
  EM_DASH,
  formatDuration,
  formatTs,
  shortenId,
  type TaskDetail,
  VIEW_BASE,
} from '../constants';

interface Props {
  execution: TaskDetail;
  className?: string;
}

interface Fact {
  label: string;
  value: ReactNode;
}

/**
 * One label/value pair.
 *
 * Two shapes, one component: a bordered tile in a two-column grid on phones,
 * where a 320px sidebar has nowhere to go, and a plain justified row on
 * desktop where the card *is* the sidebar. Splitting it into two components
 * would mean two places to forget a field.
 */
function FactRow({ label, value }: Fact) {
  return (
    <div className="rounded-xl border bg-card p-3 lg:flex lg:justify-between lg:gap-3 lg:rounded-none lg:border-0 lg:bg-transparent lg:p-0">
      <dt className="text-xs text-muted-foreground lg:text-[13px]">{label}</dt>
      <dd className="mt-1 min-w-0 text-sm lg:mt-0 lg:text-right lg:text-[13px]">{value}</dd>
    </div>
  );
}

/** The Details card: what ran, where, and when, with the exception pinned last. */
export function DetailFacts({ execution, className }: Props) {
  const { t } = useT();

  const facts: Fact[] = [
    { label: t(keys.background_tasks.detail.queue), value: execution.queue },
    {
      label: t(keys.background_tasks.detail.worker),
      value: execution.worker ? (
        <code className="font-mono text-xs">{execution.worker}</code>
      ) : (
        EM_DASH
      ),
    },
    {
      label: t(keys.background_tasks.detail.celery_id),
      // Copyable rather than shortened text: the id's only use is being pasted
      // into a log query, and a truncated one cannot be retyped from.
      value: execution.celery_task_id ? (
        <CopyableId value={execution.celery_task_id} label={shortenId(execution.celery_task_id)} />
      ) : (
        EM_DASH
      ),
    },
    { label: t(keys.background_tasks.detail.queued_at), value: formatTs(execution.queued_at) },
    { label: t(keys.background_tasks.detail.started_at), value: formatTs(execution.started_at) },
    { label: t(keys.background_tasks.detail.finished_at), value: formatTs(execution.finished_at) },
    {
      label: t(keys.background_tasks.detail.duration),
      value: formatDuration(execution.started_at, execution.finished_at),
    },
    { label: t(keys.background_tasks.detail.heartbeat), value: formatTs(execution.heartbeat_at) },
    {
      label: t(keys.background_tasks.detail.retried_from),
      value: execution.retried_from_id ? (
        <Link
          href={`${VIEW_BASE}/${execution.retried_from_id}`}
          className="font-mono text-xs text-primary-700 hover:underline"
        >
          {shortenId(execution.retried_from_id)}
        </Link>
      ) : (
        EM_DASH
      ),
    },
  ];

  return (
    <Card
      className={`gap-3 border-0 bg-transparent p-0 shadow-none lg:h-full lg:border lg:bg-card lg:p-5 ${className ?? ''}`}
    >
      <h2 className="hidden text-base font-bold font-display lg:block">
        {t(keys.background_tasks.detail.meta)}
      </h2>
      <dl className="grid grid-cols-2 gap-3 lg:block lg:space-y-2.5">
        {facts.map((fact) => (
          <FactRow key={fact.label} label={fact.label} value={fact.value} />
        ))}
      </dl>
      {/* Pinned to the foot of the card: the exception is the answer to "why
          am I on this page", and it should be in the same place every time
          rather than sliding around with the row count above it. */}
      <div className="mt-auto flex flex-col gap-1.5 rounded-xl border bg-card p-3 lg:rounded-none lg:border-0 lg:border-t lg:bg-transparent lg:p-0 lg:pt-3.5">
        <span className="text-xs text-muted-foreground lg:text-[12.5px]">
          {t(keys.background_tasks.detail.exception)}
        </span>
        {execution.exception_type ? (
          <code className="break-all font-mono text-xs leading-relaxed text-red-700">
            {execution.exception_type}
          </code>
        ) : (
          <span className="text-sm text-muted-foreground">{EM_DASH}</span>
        )}
      </div>
    </Card>
  );
}
