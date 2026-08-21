import { Head, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
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
import { usePermissions } from '@simple-module-py/ui/hooks/use-permissions';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { Flag, RotateCcw } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import { TenantPicker } from './components/TenantPicker';
import { type PendingToggle, ToggleConfirmDialog } from './components/ToggleConfirmDialog';

interface FeatureFlag {
  name: string;
  description: string;
  default_enabled: boolean;
  enabled: boolean;
  overridden: boolean;
  system_enabled: boolean | null;
}

interface Props {
  flags: FeatureFlag[];
  tenant_id: string | null;
  tenants: string[];
}

function buildPath(tenantId: string | null) {
  return tenantId
    ? `/admin/feature-flags?tenant_id=${encodeURIComponent(tenantId)}`
    : '/admin/feature-flags';
}

function actionUrl(name: string, action: 'toggle' | 'clear', tenantId: string | null) {
  const base = `/admin/feature-flags/${name}/${action}`;
  return tenantId ? `${base}?tenant_id=${encodeURIComponent(tenantId)}` : base;
}

function Browse() {
  const { flags, tenant_id, tenants } = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();
  const { can } = usePermissions();
  const canManage = can('feature_flags.manage');

  // The switch stages the change; the confirm is what writes it. The Switch
  // stays bound to the server value, so cancelling leaves it where it was
  // without needing to undo anything.
  const [pending, setPending] = useState<PendingToggle | null>(null);

  function handleToggle({ name, next }: PendingToggle) {
    setPending(null);
    router.post(
      actionUrl(name, 'toggle', tenant_id),
      { enabled: next },
      {
        preserveScroll: true,
        onSuccess: () =>
          toast.success(
            next
              ? t(keys.feature_flags.toasts.enabled, { name })
              : t(keys.feature_flags.toasts.disabled, { name }),
          ),
        onError: () => toast.error(t(keys.feature_flags.toasts.toggle_failed)),
      },
    );
  }

  function handleClear(flag: FeatureFlag) {
    router.post(
      actionUrl(flag.name, 'clear', tenant_id),
      {},
      {
        preserveScroll: true,
        onSuccess: () => toast.success(t(keys.feature_flags.toasts.cleared, { name: flag.name })),
        onError: () => toast.error(t(keys.feature_flags.toasts.toggle_failed)),
      },
    );
  }

  return (
    <>
      <Head title="Feature Flags" />
      <PageShell
        title={t(keys.feature_flags.browse.title)}
        description={t(keys.feature_flags.browse.description)}
      >
        <Card className="mb-4 p-4">
          <TenantPicker
            tenantId={tenant_id}
            tenants={tenants}
            onSelect={(next) => router.visit(buildPath(next))}
          />
          <p className="mt-3 text-sm text-muted-foreground">
            {tenant_id
              ? t(keys.feature_flags.browse.viewing_tenant, { tenant_id })
              : t(keys.feature_flags.browse.viewing_system)}
          </p>
        </Card>

        <div className="mb-4 flex items-center justify-end">
          {flags.length > 0 && (
            <p className="text-sm text-muted-foreground">
              {t(keys.feature_flags.browse.count, { count: flags.length })}
            </p>
          )}
        </div>

        <Card className="border-border overflow-hidden p-0">
          <Table>
            <TableHeader className="bg-secondary/40">
              <TableRow>
                <TableHead className="sm:px-6 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                  {t(keys.feature_flags.table.name)}
                </TableHead>
                <TableHead className="hidden md:table-cell sm:px-6 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                  {t(keys.feature_flags.table.description)}
                </TableHead>
                <TableHead className="hidden sm:table-cell sm:px-6 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                  {t(keys.feature_flags.table.default)}
                </TableHead>
                <TableHead className="sm:px-6 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                  {t(keys.feature_flags.table.status)}
                </TableHead>
                {canManage && (
                  <TableHead className="text-right sm:px-6 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
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
                          <Badge variant="secondary">
                            {t(keys.feature_flags.table.overridden)}
                          </Badge>
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
                        onCheckedChange={(checked) =>
                          setPending({ name: flag.name, next: checked === true })
                        }
                        disabled={!canManage}
                        aria-label={flag.name}
                      />
                      <div className="flex flex-col">
                        <span className="text-sm text-muted-foreground">
                          {flag.enabled
                            ? t(keys.feature_flags.table.enabled)
                            : t(keys.feature_flags.table.disabled)}
                        </span>
                        {tenant_id && flag.system_enabled !== null && (
                          <span className="text-xs text-muted-foreground">
                            {t(keys.feature_flags.table.system_value, {
                              value: flag.system_enabled
                                ? t(keys.feature_flags.table.enabled)
                                : t(keys.feature_flags.table.disabled),
                            })}
                          </span>
                        )}
                      </div>
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
                          {tenant_id
                            ? t(keys.feature_flags.table.following_system)
                            : t(keys.feature_flags.table.following_default)}
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

        <ToggleConfirmDialog
          pending={pending}
          tenantId={tenant_id}
          onConfirm={handleToggle}
          onCancel={() => setPending(null)}
        />
      </PageShell>
    </>
  );
}

Browse.layout = (page: React.ReactNode) => <AdminLayout>{page}</AdminLayout>;
export default Browse;
