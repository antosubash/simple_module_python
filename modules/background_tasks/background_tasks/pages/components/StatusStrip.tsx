import { keys, useT } from '@simple-module-py/i18n';
import { StatCard } from '@simple-module-py/ui/components/StatCard';
import { cn } from '@simple-module-py/ui/lib/utils';
import { TASK_STATUS, type TaskStatus } from '../constants';

/** Per-status totals, plus the one windowed count the strip shows. */
export type StatusCounts = Partial<Record<TaskStatus, number>> & { success_24h?: number };

interface Props {
  counts: StatusCounts;
  /** Currently filtered status, or '' for all. */
  active: string;
  onSelect: (status: string) => void;
}

type Tone = 'default' | 'warning' | 'destructive';

type StripLabelKey = (typeof keys.background_tasks.strip)[keyof typeof keys.background_tasks.strip];

interface Tile {
  /** Status this tile narrows the table to. */
  filter: TaskStatus;
  labelKey: StripLabelKey;
  count: (counts: StatusCounts) => number;
  tone: Tone;
}

/**
 * The five numbers that describe a queue, left to right in the order work
 * moves through it: waiting, running, done, broken, wedged.
 *
 * "Succeeded 24h" is the only windowed figure, and deliberately so — the other
 * four are states something is in *right now*, while success is only
 * interesting as a rate. An all-time success total is a number that never goes
 * down and therefore never says anything.
 */
const TILES: Tile[] = [
  {
    filter: TASK_STATUS.PENDING,
    labelKey: keys.background_tasks.strip.queued,
    count: (c) => c[TASK_STATUS.PENDING] ?? 0,
    tone: 'default',
  },
  {
    filter: TASK_STATUS.RUNNING,
    labelKey: keys.background_tasks.strip.running,
    count: (c) => c[TASK_STATUS.RUNNING] ?? 0,
    tone: 'default',
  },
  {
    // Filters to `success` like every other tile, even though the number is
    // windowed: the tile is how an operator reaches the successes at all, and
    // the segmented control below has no option for them.
    filter: TASK_STATUS.SUCCESS,
    labelKey: keys.background_tasks.strip.succeeded_24h,
    count: (c) => c.success_24h ?? 0,
    tone: 'default',
  },
  {
    filter: TASK_STATUS.FAILED,
    labelKey: keys.background_tasks.strip.failed,
    count: (c) => c[TASK_STATUS.FAILED] ?? 0,
    tone: 'destructive',
  },
  {
    filter: TASK_STATUS.STUCK,
    labelKey: keys.background_tasks.strip.stuck,
    count: (c) => c[TASK_STATUS.STUCK] ?? 0,
    tone: 'warning',
  },
];

export function StatusStrip({ counts, active, onSelect }: Props) {
  const { t } = useT();
  return (
    <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {TILES.map((tile) => {
        const count = tile.count(counts);
        const isActive = active === tile.filter;
        // A permanently red zero trains people to ignore the tile, so the
        // alarm tint only appears once there is something to be alarmed by.
        const tone = count > 0 ? tile.tone : 'default';
        return (
          <button
            key={tile.labelKey}
            type="button"
            // Clicking the tile you already filtered by clears the filter, so
            // the strip can undo itself without reaching for the control below.
            onClick={() => onSelect(isActive ? '' : tile.filter)}
            aria-pressed={isActive}
            // An offset ring is drawn *outside* the tile, so on a tinted
            // Failed or Stuck card it sat in the gap and read as a second
            // border in a clashing colour. Inset, it follows the card's own
            // edge whatever colour that card is.
            className={cn(
              'cursor-pointer rounded-xl text-left transition-shadow hover:shadow-md',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              isActive && 'ring-2 ring-foreground/20 ring-inset',
            )}
          >
            <StatCard
              label={t(tile.labelKey)}
              value={count.toLocaleString()}
              tone={tone}
              className="h-full"
            />
          </button>
        );
      })}
    </div>
  );
}
