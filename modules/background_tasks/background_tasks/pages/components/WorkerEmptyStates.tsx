import { keys, useT } from '@simple-module-py/i18n';
import type { ReactNode } from 'react';

interface BoxProps {
  title: string;
  titleClassName: string;
  description: string;
  children: ReactNode;
}

/**
 * The dashed frame both fleet-empty states share.
 *
 * Dashed rather than a solid card because it is explicitly *not* a worker —
 * the outline says "this is where the fleet would be" without pretending to be
 * one more thing in it.
 */
function EmptyBox({ title, titleClassName, description, children }: BoxProps) {
  return (
    <div className="flex flex-col gap-2.5 rounded-[13px] border-[1.5px] border-dashed p-5">
      <span className={`text-[15px] font-bold font-[var(--font-display)] ${titleClassName}`}>
        {title}
      </span>
      <p className="text-[13px] leading-relaxed text-muted-foreground">{description}</p>
      {children}
    </div>
  );
}

// Literal `<code>` at each call site rather than a wrapper component: the
// untranslated-string check exempts technical literals by looking for the
// element itself, and a shell command routed through a translation catalog is
// a command someone can mistranslate into not working.
const CODE_BLOCK =
  'overflow-x-auto rounded-lg bg-secondary px-3 py-2.5 font-mono text-xs text-muted-foreground';

/**
 * The broker refused the connection, so there is no fleet to describe.
 *
 * Shows the error verbatim and the setting that produced it — with the
 * password stripped server-side — because the two together are the whole
 * diagnosis: the url says where it tried, the error says what happened.
 */
export function BrokerUnreachable({
  error,
  brokerUrl,
}: {
  error: string | null;
  brokerUrl: string;
}) {
  const { t } = useT();
  return (
    <EmptyBox
      title={t(keys.background_tasks.workers.broker_unreachable_title)}
      titleClassName="text-red-700"
      description={error ?? t(keys.background_tasks.workers.no_error_reported)}
    >
      <p className="text-[13px] leading-relaxed text-muted-foreground">
        {t(keys.background_tasks.workers.broker_unreachable_description)}
      </p>
      <code className={CODE_BLOCK}>SM_BG_TASKS_BROKER_URL={brokerUrl}</code>
    </EmptyBox>
  );
}

/** The broker answered, but nothing is consuming — so offer the command. */
export function NoWorkers({ queues }: { queues: string[] }) {
  const { t } = useT();
  const queueList = queues.join(',');
  return (
    <EmptyBox
      title={t(keys.background_tasks.workers.no_workers_title)}
      titleClassName="text-amber-700"
      description={t(keys.background_tasks.workers.no_workers_description)}
    >
      <code className={CODE_BLOCK}>
        uv run celery -A scripts.run_worker:celery worker -l info -Q {queueList}
      </code>
    </EmptyBox>
  );
}
