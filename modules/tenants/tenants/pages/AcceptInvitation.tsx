import { Head, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { AuthCardShell } from '@simple-module-py/ui/layouts/AuthCardShell';
import { TimerOff } from 'lucide-react';
import { useState } from 'react';
import { useTenantErrors } from '../hooks/useTenantErrors';

interface InvitationPreview {
  tenant_name: string;
  email: string;
  role: string;
  expired: boolean;
  accepted: boolean;
}

interface Props {
  token: string;
  invitation: InvitationPreview | null;
  signed_in_as: string | null;
}

const ROLE_KEY = keys.tenants.roles;

function AcceptInvitation() {
  const { token, invitation, signed_in_as } = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();
  const { describe } = useTenantErrors();
  const [accepting, setAccepting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function accept() {
    setAccepting(true);
    setError(null);
    try {
      const response = await fetch('/api/tenants/invitations/accept', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ token }),
      });
      if (!response.ok) {
        setError(await describe(response));
        return;
      }
      router.visit('/tenants');
    } catch {
      setError(t(keys.tenants.errors.generic));
    } finally {
      setAccepting(false);
    }
  }

  if (invitation === null || invitation.expired || invitation.accepted) {
    const title = !invitation
      ? t(keys.tenants.accept.invalid_title)
      : invitation.expired
        ? t(keys.tenants.accept.expired_title)
        : t(keys.tenants.accept.accepted_title);
    const description = !invitation
      ? t(keys.tenants.accept.invalid_description)
      : invitation.expired
        ? t(keys.tenants.accept.expired_description, { tenant: invitation.tenant_name })
        : t(keys.tenants.accept.accepted_description, { tenant: invitation.tenant_name });
    return (
      <AuthCardShell tone="destructive">
        <Head title={t(keys.tenants.accept.head_title)} />
        <div className="flex flex-col items-center gap-3 text-center">
          <TimerOff className="size-8 text-destructive" aria-hidden="true" />
          <h1 className="text-lg font-semibold">{title}</h1>
          <p className="text-sm text-muted-foreground">{description}</p>
        </div>
      </AuthCardShell>
    );
  }

  const mismatch = !!signed_in_as && signed_in_as.toLowerCase() !== invitation.email.toLowerCase();

  return (
    <AuthCardShell width="lg">
      <Head title={t(keys.tenants.accept.head_title)} />
      <h1 className="mb-3 text-lg font-semibold">
        {t(keys.tenants.accept.title, { tenant: invitation.tenant_name })}
      </h1>
      <p className="mb-4 text-sm text-muted-foreground">
        {t(keys.tenants.accept.description, {
          tenant: invitation.tenant_name,
          role: t(ROLE_KEY[invitation.role as 'owner' | 'admin' | 'member']),
        })}
      </p>

      {mismatch ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          <p className="mb-1 font-medium">{t(keys.tenants.accept.mismatch_title)}</p>
          <p>
            {t(keys.tenants.accept.mismatch_description, {
              email: invitation.email,
              signed_in_as: signed_in_as ?? '',
            })}
          </p>
        </div>
      ) : (
        <>
          {error && <p className="mb-3 text-sm text-destructive">{error}</p>}
          <Button onClick={accept} disabled={accepting} size="lg" className="w-full">
            {accepting ? t(keys.tenants.accept.accepting) : t(keys.tenants.accept.accept_button)}
          </Button>
        </>
      )}
    </AuthCardShell>
  );
}

export default AcceptInvitation;
