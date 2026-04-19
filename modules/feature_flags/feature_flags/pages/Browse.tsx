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
import { Input } from '@simple-module/ui/components/ui/input';
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
import { useState } from 'react';
import { toast } from 'sonner';

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
  return tenantId ? `/feature_flags?tenant_id=${encodeURIComponent(tenantId)}` : '/feature_flags';
}

function actionUrl(name: string, action: 'toggle' | 'clear', tenantId: string | null) {
  const base = `/feature_flags/${name}/${action}`;
  return tenantId ? `${base}?tenant_id=${encodeURIComponent(tenantId)}` : base;
}

function Browse() {
  const { flags, tenant_id, tenants } = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();
  const { can } = usePermissions();
  const canManage = can('feature_flags.manage');
  const [tenantInput, setTenantInput] = useState(tenant_id ?? '');

  function handleToggle(flag: FeatureFlag, next: boolean) {
    router.post(
      actionUrl(flag.name, 'toggle', tenant_id),
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
      actionUrl(flag.name, 'clear', tenant_id),
      {},
      {
        preserveScroll: true,
        onSuccess: () => toast.success(t(keys.feature_flags.toasts.cleared, { name: flag.name })),
        onError: () => toast.error(t(keys.feature_flags.toasts.toggle_failed)),
      },
    );
  }

  function visitTenant(value: string) {
    router.visit(buildPath(value.trim() || null));
  }

  return (
    <PageShell
      title={t(keys.feature_flags.browse.title)}
      description={t(keys.feature_flags.browse.description)}
    >
      <Card className="mb-4 p-4">
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            visitTenant(tenantInput);
          }}
        >
          <div className="flex-1 min-w-[200px]">
            <label className="block text-sm font-medium mb-1" htmlFor="tenant_id">
              {t(keys.feature_flags.browse.tenant_id_label)}
            </label>
            <Input
              id="tenant_id"
              value={tenantInput}
              onChange={(e) => setTenantInput(e.target.value)}
              placeholder={t(keys.feature_flags.browse.tenant_id_placeholder)}
            />
          </div>
          <Button type="submit" variant="default">
            {t(keys.feature_flags.browse.go)}
          </Button>
          {tenant_id && (
            <Button type="button" variant="ghost" onClick={() => visitTenant('')}>
              {t(keys.feature_flags.browse.back_to_system)}
            </Button>
          )}
        </form>
        {tenants.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
            <span className="text-muted-foreground">
              {t(keys.feature_flags.browse.tenants_with_overrides)}:
            </span>
            {tenants.map((tid) => (
              <Button
                key={tid}
                type="button"
                size="sm"
                variant={tid === tenant_id ? 'default' : 'outline'}
                onClick={() => visitTenant(tid)}
              >
                {tid}
              </Button>
            ))}
          </div>
        )}
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
    </PageShell>
  );
}

Browse.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Browse;
