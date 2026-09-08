import { useT } from '@simple-module-py/i18n';
import { cn } from '@simple-module-py/ui/lib/utils';
import { STATUS_LABEL_KEY, STATUS_PILL_CLASS, type TaskStatus } from '../constants';

interface Props {
  status: TaskStatus;
  className?: string;
}

/**
 * A task's state as a borderless tinted pill.
 *
 * One component for the table, the detail header and the phone strip, so a
 * `failed` row and a `failed` page can never end up different shades of the
 * same idea.
 */
export function StatusPill({ status, className }: Props) {
  const { t } = useT();
  return (
    <span
      className={cn(
        'inline-flex rounded-full px-2.5 py-0.5 text-[11.5px] font-medium',
        STATUS_PILL_CLASS[status],
        className,
      )}
    >
      {t(STATUS_LABEL_KEY[status])}
    </span>
  );
}
