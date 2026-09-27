import { keys, useT } from '@simple-module-py/i18n';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module-py/ui/components/ui/table';
import { useState } from 'react';
import { toast } from 'sonner';
import { useTenantErrors } from '../hooks/useTenantErrors';

export interface AdminTenant {
  id: string;
  slug: string;
  name: string;
  status: 'active' | 'suspended';
  created_at: string | null;
  members: number;
}

interface Props {
  tenants: AdminTenant[];
  onChanged: () => void;
}

const STATUS_KEY = keys.tenants.status;

/** The platform-wide organisation roster on the admin Browse page. */
export function AdminTenantsTable({ tenants, onChanged }: Props) {
  const { t } = useT();
  const { describe } = useTenantErrors();
  const [busyId, setBusyId] = useState<string | null>(null);

  async function setStatus(tenant: AdminTenant, action: 'suspend' | 'reactivate') {
    setBusyId(tenant.id);
    try {
      const response = await fetch(`/api/tenants/admin/${tenant.id}/${action}`, {
        method: 'POST',
        credentials: 'same-origin',
      });
      if (!response.ok) {
        toast.error(await describe(response));
        return;
      }
      toast.success(
        action === 'suspend'
          ? t(keys.tenants.admin.toast_suspended)
          : t(keys.tenants.admin.toast_reactivated),
      );
      onChanged();
    } catch {
      toast.error(t(keys.tenants.admin.toast_action_failed));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t(keys.tenants.admin.table_name)}</TableHead>
          <TableHead>{t(keys.tenants.admin.table_slug)}</TableHead>
          <TableHead>{t(keys.tenants.admin.table_status)}</TableHead>
          <TableHead>{t(keys.tenants.admin.table_members)}</TableHead>
          <TableHead>{t(keys.tenants.admin.table_created)}</TableHead>
          <TableHead className="text-right">{t(keys.tenants.admin.table_actions)}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {tenants.map((tenant) => (
          <TableRow key={tenant.id}>
            <TableCell className="font-medium">{tenant.name}</TableCell>
            <TableCell className="text-muted-foreground">{tenant.slug}</TableCell>
            <TableCell>
              <Badge variant={tenant.status === 'active' ? 'secondary' : 'destructive'}>
                {t(STATUS_KEY[tenant.status])}
              </Badge>
            </TableCell>
            <TableCell>{tenant.members}</TableCell>
            <TableCell className="text-muted-foreground">
              {tenant.created_at ? new Date(tenant.created_at).toLocaleDateString() : '—'}
            </TableCell>
            <TableCell className="text-right">
              {tenant.status === 'active' ? (
                <Button
                  variant="outline"
                  size="sm"
                  className="max-lg:min-h-11"
                  disabled={busyId === tenant.id}
                  onClick={() => setStatus(tenant, 'suspend')}
                >
                  {t(keys.tenants.admin.suspend_button)}
                </Button>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  className="max-lg:min-h-11"
                  disabled={busyId === tenant.id}
                  onClick={() => setStatus(tenant, 'reactivate')}
                >
                  {t(keys.tenants.admin.reactivate_button)}
                </Button>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
