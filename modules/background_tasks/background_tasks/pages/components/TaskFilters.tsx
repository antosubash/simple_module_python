import { keys, useT } from '@simple-module-py/i18n';
import { SegmentedControl } from '@simple-module-py/ui/components/SegmentedControl';
import { Input } from '@simple-module-py/ui/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@simple-module-py/ui/components/ui/select';
import { Search } from 'lucide-react';
import {
  QUEUE_ALL,
  SEGMENT_LABEL_KEY,
  SEGMENT_STATUSES,
  STATUS_ALL,
  TENANT_ALL,
} from '../constants';

interface Props {
  search: string;
  onSearchChange: (next: string) => void;
  /** Active status, or `STATUS_ALL`. */
  status: string;
  onStatusChange: (next: string) => void;
  /** Active queue, or `QUEUE_ALL`. */
  queue: string;
  onQueueChange: (next: string) => void;
  /** Every queue that has run work, for the dropdown. */
  queues: string[];
  /** Active tenant filter, or `TENANT_ALL`. */
  tenant: string;
  onTenantChange: (next: string) => void;
  /** Tenants that have published work, for the dropdown. */
  tenantIds: string[];
  /** Filter value selecting executions with no tenant (platform publishes). */
  platformTenantValue: string;
}

/**
 * One row: free-text search, the status the operator is triaging, the queue
 * they are triaging it in.
 *
 * Status is segmented rather than a dropdown because there are four options
 * and the answer is always visible; queue is a dropdown because the list is
 * whatever this install happens to route through and can be long.
 */
export function TaskFilters({
  search,
  onSearchChange,
  status,
  onStatusChange,
  queue,
  onQueueChange,
  queues,
  tenant,
  onTenantChange,
  tenantIds,
  platformTenantValue,
}: Props) {
  const { t } = useT();
  const options = SEGMENT_STATUSES.map((value) => ({
    value: value as string,
    label: t(SEGMENT_LABEL_KEY[value]),
  }));

  return (
    <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center">
      <div className="relative flex-1">
        <Search
          className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <Input
          placeholder={t(keys.background_tasks.index.search_placeholder)}
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="pl-9 max-lg:min-h-11"
        />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <SegmentedControl
          value={status || STATUS_ALL}
          onChange={(next) => onStatusChange(next)}
          options={options}
          aria-label={t(keys.background_tasks.filters.status_label)}
        />
        <Select value={queue || QUEUE_ALL} onValueChange={onQueueChange}>
          <SelectTrigger
            aria-label={t(keys.background_tasks.filters.queue_aria)}
            className="gap-1.5 max-lg:min-h-11"
          >
            <span className="text-muted-foreground">
              {t(keys.background_tasks.filters.queue_label)}
            </span>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={QUEUE_ALL}>{t(keys.background_tasks.filters.queue_all)}</SelectItem>
            {queues.map((q) => (
              <SelectItem key={q} value={q} className="font-mono">
                {q}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={tenant || TENANT_ALL} onValueChange={onTenantChange}>
          <SelectTrigger
            aria-label={t(keys.background_tasks.filters.tenant_aria)}
            className="gap-1.5 max-lg:min-h-11"
          >
            <span className="text-muted-foreground">
              {t(keys.background_tasks.filters.tenant_label)}
            </span>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={TENANT_ALL}>
              {t(keys.background_tasks.filters.tenant_all)}
            </SelectItem>
            <SelectItem value={platformTenantValue}>
              {t(keys.background_tasks.filters.tenant_platform)}
            </SelectItem>
            {tenantIds.map((id) => (
              <SelectItem key={id} value={id} className="font-mono">
                {id}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
