import { keys, useT } from '@simple-module-py/i18n';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { Building2 } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import { useTenantErrors } from '../hooks/useTenantErrors';

export interface Membership {
  id: string;
  slug: string;
  name: string;
  status: 'active' | 'suspended';
  role: 'owner' | 'admin' | 'member';
  created_at: string | null;
}

interface Props {
  memberships: Membership[];
  activeId: string | null;
  onSwitched: () => void;
}

const ROLE_KEY = keys.tenants.roles;
const STATUS_KEY = keys.tenants.status;

/** The list of organisations the current user belongs to, on the Index page. */
export function MembershipList({ memberships, activeId, onSwitched }: Props) {
  const { t } = useT();
  const { describe } = useTenantErrors();
  const [switching, setSwitching] = useState<string | null>(null);

  async function handleSwitch(id: string) {
    setSwitching(id);
    try {
      const response = await fetch(`/api/tenants/${id}/switch`, {
        method: 'POST',
        credentials: 'same-origin',
      });
      if (!response.ok) {
        toast.error(await describe(response));
        return;
      }
      toast.success(t(keys.tenants.index.toast_switched));
      onSwitched();
    } catch {
      toast.error(t(keys.tenants.index.toast_switch_failed));
    } finally {
      setSwitching(null);
    }
  }

  return (
    <div className="space-y-3">
      {memberships.map((membership) => {
        const isActive = membership.id === activeId;
        const isSuspended = membership.status === 'suspended';
        return (
          <Card key={membership.id} className="flex-row items-center justify-between gap-4 p-4">
            <div className="flex min-w-0 items-center gap-3">
              <Building2 className="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate font-medium">{membership.name}</span>
                  {isActive && (
                    <Badge variant="secondary">{t(keys.tenants.index.active_badge)}</Badge>
                  )}
                  {isSuspended && <Badge variant="destructive">{t(STATUS_KEY.suspended)}</Badge>}
                </div>
                <div className="text-xs text-muted-foreground">
                  {membership.slug} · {t(ROLE_KEY[membership.role])}
                </div>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {isActive && (
                <Button asChild variant="outline" size="sm" className="max-lg:min-h-11">
                  <a href="/tenants/members">{t(keys.tenants.index.members_link)}</a>
                </Button>
              )}
              {!isActive && !isSuspended && (
                <Button
                  size="sm"
                  className="max-lg:min-h-11"
                  disabled={switching === membership.id}
                  onClick={() => handleSwitch(membership.id)}
                >
                  {t(keys.tenants.index.switch_button)}
                </Button>
              )}
            </div>
          </Card>
        );
      })}
    </div>
  );
}
