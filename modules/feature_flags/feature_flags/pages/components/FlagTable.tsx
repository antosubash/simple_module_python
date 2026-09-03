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

  return (
    <Card className="gap-0 border-border overflow-hidden p-0">
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
              <TableHead className={cn(HEAD, 'text-right')}>
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
              </TableCell>
              {canManage && (
                <TableCell className="text-right sm:px-6">
                  {flag.overridden ? (
                    <Button
                      variant="link"
                      size="sm"
                      className="h-auto p-0 text-primary-700"
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
                  )}
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
      <p className="border-t px-4 py-3 text-sm text-muted-foreground">
        {t(keys.feature_flags.browse.audit_note)}
      </p>
    </Card>
  );
}
