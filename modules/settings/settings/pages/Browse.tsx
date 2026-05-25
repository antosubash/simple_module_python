import { Head, router } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module-py/ui/components/ui/table';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import { Box, Plus, Settings as SettingsIcon } from 'lucide-react';
import type React from 'react';
import type { ValueType } from './components/ValueInput';
import { ROUTES } from './routes';

type Scope = 'system' | 'tenant' | 'user';

type Setting = {
  id: number;
  scope: Scope;
  scope_id: string;
  key: string;
  value: string;
  value_type: ValueType;
  description: string | null;
};

type Props = { settings: Setting[] };

const SCOPE_TONE: Record<Scope, string> = {
  system: 'border-primary-200 bg-primary-50 text-primary-700',
  tenant: 'border-blue-200 bg-blue-50 text-blue-700',
  user: 'border-amber-200 bg-amber-50 text-amber-700',
};

function Browse({ settings }: Props) {
  const { t } = useT();

  function handleDelete(setting: Setting) {
    if (!window.confirm(t(keys.settings.browse.delete_confirm, { key: setting.key }))) return;
    router.delete(ROUTES.byId(setting.id));
  }

  return (
    <>
      <Head title="Settings" />
      <PageShell
        title={t(keys.settings.browse.title)}
        description="Workspace, account, mailer, and module configuration."
        actions={
          <>
            <Button asChild variant="outline" className="gap-1.5">
              <a href={ROUTES.modules}>
                <Box className="h-3.5 w-3.5" /> {t(keys.settings.modules.browse_link)}
              </a>
            </Button>
            <Button asChild className="gap-1.5">
              <a href={ROUTES.create}>
                <Plus className="h-4 w-4" />
                {t(keys.settings.browse.new_button)}
              </a>
            </Button>
          </>
        }
      >
        {settings.length === 0 ? (
          <Card className="border-border">
            <div className="flex flex-col items-center gap-2 py-16 text-muted-foreground">
              <SettingsIcon className="size-8" />
              <h2 className="text-base font-semibold text-foreground font-[var(--font-display)]">
                {t(keys.settings.browse.empty_title)}
              </h2>
              <p className="text-sm">{t(keys.settings.browse.empty_description)}</p>
            </div>
          </Card>
        ) : (
          <Card className="border-border overflow-hidden p-0">
            <Table>
              <TableHeader className="bg-secondary/40">
                <TableRow>
                  <TableHead className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    {t(keys.settings.table.scope)}
                  </TableHead>
                  <TableHead className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground hidden md:table-cell">
                    {t(keys.settings.table.scope_id)}
                  </TableHead>
                  <TableHead className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    {t(keys.settings.table.key)}
                  </TableHead>
                  <TableHead className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground hidden lg:table-cell">
                    {t(keys.settings.table.value_type)}
                  </TableHead>
                  <TableHead className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    {t(keys.settings.table.value)}
                  </TableHead>
                  <TableHead className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground hidden lg:table-cell">
                    {t(keys.settings.table.description)}
                  </TableHead>
                  <TableHead className="text-right">{t(keys.settings.table.actions)}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {settings.map((setting) => (
                  <TableRow key={setting.id} className="hover:bg-secondary/40">
                    <TableCell>
                      <Badge variant="outline" className={SCOPE_TONE[setting.scope]}>
                        {t(keys.settings.scopes[setting.scope])}
                      </Badge>
                    </TableCell>
                    <TableCell className="hidden md:table-cell font-mono text-xs text-muted-foreground">
                      {setting.scope_id || '—'}
                    </TableCell>
                    <TableCell className="font-mono text-sm font-semibold">{setting.key}</TableCell>
                    <TableCell className="hidden lg:table-cell text-[11px] uppercase tracking-[0.08em] text-muted-foreground">
                      {t(keys.settings.value_types[setting.value_type])}
                    </TableCell>
                    <TableCell className="font-mono text-xs text-foreground max-w-[200px] truncate">
                      {setting.value}
                    </TableCell>
                    <TableCell className="hidden lg:table-cell text-sm text-muted-foreground max-w-[200px] truncate">
                      {setting.description ?? ''}
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-3 text-xs">
                        <a
                          href={ROUTES.edit(setting.id)}
                          className="font-semibold text-primary-700 hover:text-primary-800"
                        >
                          {t(keys.settings.browse.edit_link)}
                        </a>
                        <button
                          type="button"
                          onClick={() => handleDelete(setting)}
                          className="font-semibold text-destructive hover:underline"
                        >
                          {t(keys.settings.browse.delete_link)}
                        </button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        )}
      </PageShell>
    </>
  );
}

Browse.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Browse;
