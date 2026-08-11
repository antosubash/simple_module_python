import { TASK_STATUS, type TaskStatus } from '../constants';
import { statusLabel } from './ExecutionRow';

export type StatusCounts = Partial<Record<TaskStatus, number>>;

interface Props {
  counts: StatusCounts;
  /** Currently filtered status, or '' for all. */
  active: string;
  onSelect: (status: string) => void;
}

/**
 * Statuses worth a dedicated tile, in the order an operator triages them.
 * Failed and stuck lead because they are the reason anyone opens this page.
 */
const TILES: TaskStatus[] = [
  TASK_STATUS.FAILED,
  TASK_STATUS.STUCK,
  TASK_STATUS.RETRYING,
  TASK_STATUS.RUNNING,
  TASK_STATUS.PENDING,
  TASK_STATUS.SUCCESS,
];

/** Tiles that mean "someone needs to look at this" get an alarm colour, but
 *  only when they are non-zero — a permanently red zero trains people to
 *  ignore it. */
const ALARMING = new Set<TaskStatus>([TASK_STATUS.FAILED, TASK_STATUS.STUCK]);

export function StatusStrip({ counts, active, onSelect }: Props) {
  return (
    <div className="mb-4 grid grid-cols-3 gap-2 sm:grid-cols-6">
      {TILES.map((status) => {
        const count = counts[status] ?? 0;
        const isActive = active === status;
        const alarm = ALARMING.has(status) && count > 0;
        return (
          <button
            key={status}
            type="button"
            aria-pressed={isActive}
            // Clicking the tile you already filtered by clears the filter,
            // so the strip can undo itself without reaching for the dropdown.
            onClick={() => onSelect(isActive ? '' : status)}
            className={[
              'rounded-lg border px-3 py-2 text-left transition-colors',
              isActive
                ? 'border-primary bg-accent'
                : 'border-border bg-card hover:border-primary/40 hover:bg-accent/50',
            ].join(' ')}
          >
            <div
              className={`text-lg font-semibold tabular-nums leading-tight ${
                alarm ? 'text-red-600 dark:text-red-400' : 'text-foreground'
              }`}
            >
              {count}
            </div>
            <div className="truncate text-[11px] text-muted-foreground">{statusLabel(status)}</div>
          </button>
        );
      })}
    </div>
  );
}
