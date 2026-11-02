import { keys, useT } from '@simple-module-py/i18n';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import {
  Empty,
  EmptyDescription,
  EmptyMedia,
  EmptyTitle,
} from '@simple-module-py/ui/components/ui/empty';
import { Switch } from '@simple-module-py/ui/components/ui/switch';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module-py/ui/components/ui/table';
import { cn } from '@simple-module-py/ui/lib/utils';
import { Flag } from 'lucide-react';
import type { FeatureFlag } from '../types';

interface Props {
  flags: FeatureFlag[];
  /** Non-null while a tenant scope is selected; changes the fallback copy. */
  tenantId: string | null;
  canManage: boolean;
  onToggle: (flag: FeatureFlag, next: boolean) => void;
  onClear: (flag: FeatureFlag) => void;
}

const HEAD =
  'bg-secondary/40 text-[11px] font-semibold uppercase tracking-[0.08em] ' +
  'text-muted-foreground sm:px-6';

export function FlagTable({ flags, tenantId, canManage, onToggle, onClear }: Props) {
  const { t } = useT();
  const columnCount = canManage ? 5 : 4;

  /** The override control, or the sentence explaining why there is none. */
  const clearAction = (flag: FeatureFlag) =>
    flag.overridden ? (
      <Button
        variant="link"
        size="sm"
        className="h-auto p-0 text-primary-700 max-sm:min-h-11"
        onClick={() => onClear(flag)}
      >
        {t(keys.feature_flags.table.clear_override)}
      </Button>
    ) : (
      <span className="text-xs text-muted-foreground">
        {tenantId
          ? t(keys.feature_flags.table.following_system)
          : t(keys.feature_flags.table.following_default)}
      </span>
    );

  return (
    // Fills the viewport with the audit note pinned to the bottom, as the deck
    // and the settings store both do. A min-height, not a fixed one, so a long
    // flag list grows rather than scrolling inside the card.
    <Card className="flex flex-col gap-0 overflow-hidden border-border p-0 lg:min-h-[calc(100vh-var(--app-chrome-h)-15rem)]">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className={HEAD}>{t(keys.feature_flags.table.name)}</TableHead>
            <TableHead className={cn(HEAD, 'hidden md:table-cell')}>
              {t(keys.feature_flags.table.description)}
            </TableHead>
            <TableHead className={cn(HEAD, 'hidden sm:table-cell')}>
              {t(keys.feature_flags.table.system)}
            </TableHead>
            <TableHead className={HEAD}>{t(keys.feature_flags.table.effective)}</TableHead>
            {canManage && (
              // Hidden below `sm`: at 390px this column pushed the table wider
              // than the card. Its control moves under the switch instead.
              <TableHead className={cn(HEAD, 'hidden text-right sm:table-cell')}>
                {t(keys.feature_flags.table.actions)}
              </TableHead>
            )}
          </TableRow>
        </TableHeader>
        <TableBody>
          {flags.map((flag) => (
            <TableRow key={flag.name} className={cn(flag.overridden && 'bg-primary-600/10')}>
              <TableCell className="sm:px-6">
                <div className="flex flex-wrap items-center gap-2">
                  <code className="font-mono text-sm font-medium">{flag.name}</code>
                  {flag.overridden && (
                    <Badge variant="outline" className="border-primary text-primary-700">
                      {t(keys.feature_flags.table.overridden)}
                    </Badge>
                  )}
                </div>
              </TableCell>
              <TableCell className="hidden md:table-cell sm:px-6">
                <span className="line-clamp-2 text-sm text-muted-foreground">
                  {flag.description || '—'}
                </span>
              </TableCell>
              {/* The value every tenant inherits: the system override when one
                  exists, otherwise the default the module shipped. */}
              <TableCell className="hidden sm:table-cell sm:px-6 text-sm text-muted-foreground">
                {(flag.system_enabled ?? flag.default_enabled)
                  ? t(keys.feature_flags.table.on)
                  : t(keys.feature_flags.table.off)}
              </TableCell>
              <TableCell className="sm:px-6">
                <div className="flex items-center gap-3">
                  <Switch
                    checked={flag.enabled}
                    onCheckedChange={(checked) => onToggle(flag, checked === true)}
                    disabled={!canManage}
                    aria-label={flag.name}
                  />
                  <span
                    className={cn(
                      'text-sm',
                      flag.enabled ? 'font-medium' : 'text-muted-foreground',
                    )}
                  >
                    {flag.enabled
                      ? t(keys.feature_flags.table.enabled)
                      : t(keys.feature_flags.table.disabled)}
                  </span>
                </div>
                {canManage && <div className="mt-1.5 sm:hidden">{clearAction(flag)}</div>}
              </TableCell>
              {canManage && (
                <TableCell className="hidden text-right sm:table-cell sm:px-6">
                  {clearAction(flag)}
                </TableCell>
              )}
            </TableRow>
          ))}
          {/* The deck has no empty state — it never shows an install with no
              modules registering flags. This one does exist. */}
          {flags.length === 0 && (
            <TableRow>
              <TableCell colSpan={columnCount} className="h-40">
                <Empty>
                  <EmptyMedia variant="icon">
                    <Flag className="size-5 text-primary-300" />
                  </EmptyMedia>
                  <EmptyTitle>{t(keys.feature_flags.browse.empty_title)}</EmptyTitle>
                  <EmptyDescription>
                    {t(keys.feature_flags.browse.empty_description)}
                  </EmptyDescription>
                </Empty>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      <p className="mt-auto border-t px-4 py-3 text-sm text-muted-foreground">
        {t(keys.feature_flags.browse.audit_note)}
      </p>
    </Card>
  );
}
