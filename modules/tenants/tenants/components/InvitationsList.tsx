import { activeLocale, keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@simple-module-py/ui/components/ui/card';
import { apiResult } from '@simple-module-py/ui/lib/api';
import { X } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import { useTenantErrors } from '../hooks/useTenantErrors';
import { api } from '../pages/api';

export interface Invitation {
  id: number;
  email: string;
  role: 'owner' | 'admin' | 'member';
  expires_at: string;
  accepted_at: string | null;
}

interface Props {
  invitations: Invitation[];
  onChanged: () => void;
}

const ROLE_KEY = keys.tenants.roles;

/** Pending invitations on the Members page, with a revoke action per row. */
export function InvitationsList({ invitations, onChanged }: Props) {
  const { t } = useT();
  const { describe } = useTenantErrors();
  const [revokingId, setRevokingId] = useState<number | null>(null);

  const pending = invitations.filter((i) => !i.accepted_at);

  async function revoke(id: number) {
    setRevokingId(id);
    const result = await apiResult(
      api.DELETE('/api/tenants/current/invitations/{invitation_id}', {
        params: { path: { invitation_id: id } },
      }),
    );
    setRevokingId(null);
    if (!result.ok) {
      toast.error(describe(result));
      return;
    }
    toast.success(t(keys.tenants.members.toast_revoked));
    onChanged();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t(keys.tenants.members.pending_title)}</CardTitle>
      </CardHeader>
      <CardContent>
        {pending.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t(keys.tenants.members.pending_empty)}</p>
        ) : (
          <ul className="divide-y">
            {pending.map((invitation) => (
              <li key={invitation.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{invitation.email}</div>
                  <div className="text-xs text-muted-foreground">
                    {t(ROLE_KEY[invitation.role])} ·{' '}
                    {t(keys.tenants.members.pending_expires, {
                      date: new Date(invitation.expires_at).toLocaleDateString(activeLocale()),
                    })}
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-destructive max-lg:min-h-11"
                  disabled={revokingId === invitation.id}
                  onClick={() => revoke(invitation.id)}
                >
                  <X className="size-4" aria-hidden="true" />
                  {t(keys.tenants.members.revoke_button)}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
