import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Calendar } from '@simple-module-py/ui/components/ui/calendar';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@simple-module-py/ui/components/ui/popover';
import { CalendarDays } from 'lucide-react';
import type { DateRange } from 'react-day-picker';
import { formatDateRange, parseIsoDate, toIsoDate } from './format';

export interface DateRangeValue {
  from: string;
  to: string;
}

interface DateRangeFieldProps {
  id: string;
  value: DateRangeValue;
  onChange: (next: DateRangeValue) => void;
}

/**
 * One "Date range" control in place of the two `datetime-local` inputs.
 *
 * Date-only on purpose. Nobody investigating an incident narrows it to the
 * minute from this screen — they pick a couple of days and read — and asking
 * for a time was two more fields to fill and two more ways to exclude the very
 * rows being looked for. The server compensates by treating the upper bound as
 * the end of its day.
 */
export function DateRangeField({ id, value, onChange }: DateRangeFieldProps) {
  const { t } = useT();
  const from = parseIsoDate(value.from) ?? undefined;
  const to = parseIsoDate(value.to) ?? undefined;
  const label = formatDateRange(value.from || null, value.to || null);

  function handleSelect(range: DateRange | undefined) {
    onChange({
      from: range?.from ? toIsoDate(range.from) : '',
      to: range?.to ? toIsoDate(range.to) : '',
    });
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          className="w-full justify-between font-normal max-lg:min-h-11"
        >
          <span className={label ? '' : 'text-muted-foreground'}>
            {label || t(keys.audit_log.filters.date_range_any)}
          </span>
          <CalendarDays className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="range"
          autoFocus
          defaultMonth={from}
          selected={from ? { from, to } : undefined}
          onSelect={handleSelect}
        />
        <div className="border-t p-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="w-full"
            onClick={() => handleSelect(undefined)}
          >
            {t(keys.audit_log.filters.date_range_reset)}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
