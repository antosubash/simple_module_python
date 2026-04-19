import { router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module/i18n';
import { PageShell } from '@simple-module/ui/components/PageShell';
import { Badge } from '@simple-module/ui/components/ui/badge';
import { Button } from '@simple-module/ui/components/ui/button';
import { Card } from '@simple-module/ui/components/ui/card';
import {
  Empty,
  EmptyDescription,
  EmptyMedia,
  EmptyTitle,
} from '@simple-module/ui/components/ui/empty';
import { Switch } from '@simple-module/ui/components/ui/switch';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module/ui/components/ui/table';
import { usePermissions } from '@simple-module/ui/hooks/use-permissions';
import { AuthenticatedLayout } from '@simple-module/ui/layouts/AuthenticatedLayout';
import { Flag, RotateCcw } from 'lucide-react';
import { toast } from 'sonner';

interface FeatureFlag {
  name: string;
  description: string;
  default_enabled: boolean;
  enabled: boolean;
  overridden: boolean;
}

interface Props {
  flags: FeatureFlag[];
}

function Browse() {
  const { flags } = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();
  const { can } = usePermissions();
  const canManage = can('feature_flags.manage');

  function handleToggle(flag: FeatureFlag, next: boolean) {
    router.post(
      `/feature_flags/${flag.name}/toggle`,
      { enabled: next },
      {
        preserveScroll: true,
        onSuccess: () =>
          toast.success(
            next
              ? t(keys.feature_flags.toasts.enabled, { name: flag.name })
              : t(keys.feature_flags.toasts.disabled, { name: flag.name }),
          ),
        onError: () => toast.error(t(keys.feature_flags.toasts.toggle_failed)),
      },
    );
  }

  function handleClear(flag: FeatureFlag) {
    router.post(
      `/feature_flags/${flag.name}/clear`,
      {},
      {
        preserveScroll: true,
        onSuccess: () => toast.success(t(keys.feature_flags.toasts.cleared, { name: flag.name })),
        onError: () => toast.error(t(keys.feature_flags.toasts.toggle_failed)),
      },
    );
  }

  return (
    <PageShell
      title={t(keys.feature_flags.browse.title)}
      description={t(keys.feature_flags.browse.description)}
    >
      <div className="mb-4 flex items-center justify-end">
        {flags.length > 0 && (
          <p className="text-sm text-muted-foreground">
            {t(keys.feature_flags.browse.count, { count: flags.length })}
          </p>
        )}
      </div>

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="sm:px-6">{t(keys.feature_flags.table.name)}</TableHead>
              <TableHead className="hidden md:table-cell sm:px-6">
                {t(keys.feature_flags.table.description)}
              </TableHead>
              <TableHead className="hidden sm:table-cell sm:px-6">
                {t(keys.feature_flags.table.default)}
              </TableHead>
              <TableHead className="sm:px-6">{t(keys.feature_flags.table.status)}</TableHead>
              {canManage && (
                <TableHead className="text-right sm:px-6">
                  {t(keys.feature_flags.table.actions)}
                </TableHead>
              )}
            </TableRow>
          </TableHeader>
          <TableBody>
            {flags.map((flag) => (
              <TableRow key={flag.name}>
                <TableCell className="sm:px-6">
                  <div>
                    <span className="font-medium font-mono text-sm">{flag.name}</span>
                    {flag.overridden && (
                      <span className="ml-2 inline-block">
                        <Badge variant="secondary">{t(keys.feature_flags.table.overridden)}</Badge>
                      </span>
                    )}
                  </div>
                </TableCell>
                <TableCell className="hidden md:table-cell sm:px-6">
                  <span className="text-muted-foreground text-sm line-clamp-2">
                    {flag.description || '—'}
                  </span>
                </TableCell>
                <TableCell className="hidden sm:table-cell sm:px-6">
                  <span className="text-muted-foreground text-sm">
                    {flag.default_enabled
                      ? t(keys.feature_flags.table.enabled)
                      : t(keys.feature_flags.table.disabled)}
                  </span>
                </TableCell>
                <TableCell className="sm:px-6">
                  <div className="flex items-center gap-3">
                    <Switch
                      checked={flag.enabled}
                      onCheckedChange={(checked) => handleToggle(flag, checked === true)}
                      disabled={!canManage}
                      aria-label={flag.name}
                    />
                    <span className="text-sm text-muted-foreground">
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
                        variant="ghost"
                        size="sm"
                        onClick={() => handleClear(flag)}
                        title={t(keys.feature_flags.table.clear_override)}
                      >
                        <RotateCcw />
                        <span className="sr-only">
                          {t(keys.feature_flags.table.clear_override)}
                        </span>
                      </Button>
                    ) : (
                      <span className="text-xs text-muted-foreground">
                        {t(keys.feature_flags.table.following_default)}
                      </span>
                    )}
                  </TableCell>
                )}
              </TableRow>
            ))}
            {flags.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="h-40">
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
      </Card>
    </PageShell>
  );
}

Browse.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Browse;
