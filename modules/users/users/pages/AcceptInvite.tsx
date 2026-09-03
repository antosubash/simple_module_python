import { Head, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { AuthCardShell } from '@simple-module-py/ui/layouts/AuthCardShell';
import { LOGIN_PATH } from '@simple-module-py/ui/lib/auth-routes';
import { BRAND_DEFAULT_APP_NAME } from '@simple-module-py/ui/lib/brand';
import { TimerOff } from 'lucide-react';
import { useState } from 'react';
import { AuthField } from '../auth_local/components/AuthField';
import { AuthIntro } from '../auth_local/components/AuthIntro';
import { AuthStateCard } from '../auth_local/components/AuthStateCard';
import { InviteSummary } from '../auth_local/components/InviteSummary';
import { PasswordFields } from '../auth_local/components/PasswordFields';

const DASHBOARD_PATH = '/dashboard/';

interface InvitePreview {
  email: string;
  roles: string[];
  already_accepted: boolean;
  /** Display name of whoever minted the invite; absent on older tokens. */
  invited_by_name: string | null;
  expires_at: string | null;
  full_name: string | null;
}

interface Props {
  token: string;
  /** null when the token cannot be read — expired, tampered, or absent. */
  invite: InvitePreview | null;
  branding?: { appName: string } | null;
}

function AcceptInvite() {
  const { token, invite, branding } = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();

  const [fullName, setFullName] = useState(invite?.full_name ?? '');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [mismatch, setMismatch] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setMismatch(true);
      return;
    }
    setMismatch(false);
    setLoading(true);
    fetch('/api/users/auth/accept-invite', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, password, full_name: fullName }),
    })
      .then(async (res) => {
        if (res.status === 204 || res.status === 200) {
          router.visit(DASHBOARD_PATH);
        } else {
          const data = await res.json().catch(() => ({}));
          const detail = typeof data?.detail === 'string' ? data.detail : '';
          if (detail === 'INVITE_BAD_TOKEN') {
            setError(t(keys.users.accept_invite.error_bad_token));
          } else {
            setError(detail || t(keys.users.accept_invite.error_failed));
          }
        }
      })
      .catch(() => setError(t(keys.users.common.error_try_again)))
      .finally(() => setLoading(false));
  };

  if (!invite) {
    return (
      <AuthCardShell>
        <Head title={t(keys.users.accept_invite.head_title)} />
        <AuthStateCard
          icon={TimerOff}
          tone="destructive"
          title={t(keys.users.accept_invite.expired_title)}
          description={t(keys.users.accept_invite.expired_body)}
        >
          <Button variant="outline" asChild className="max-lg:min-h-11">
            <a href={LOGIN_PATH}>{t(keys.users.common.back_to_sign_in)}</a>
          </Button>
        </AuthStateCard>
      </AuthCardShell>
    );
  }

  const appName = branding?.appName ?? BRAND_DEFAULT_APP_NAME;
  const intro = (
    <AuthIntro
      heading={
        invite.invited_by_name
          ? t(keys.users.accept_invite.invited_by, {
              inviter: invite.invited_by_name,
              app: appName,
            })
          : t(keys.users.accept_invite.invited_generic, { app: appName })
      }
      body={t(keys.users.accept_invite.subtitle)}
    >
      <InviteSummary email={invite.email} roles={invite.roles} expiresAt={invite.expires_at} />
    </AuthIntro>
  );

  return (
    <AuthCardShell variant="split-light" aside={intro} width="lg">
      <Head title={t(keys.users.accept_invite.head_title)} />
      <h1 className="mb-5 text-[21px] font-bold tracking-tight text-foreground font-[var(--font-display)]">
        {t(keys.users.accept_invite.heading)}
      </h1>
      {invite.already_accepted && (
        <p className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-[13px] text-amber-700">
          {t(keys.users.accept_invite.already_used)}
        </p>
      )}
      <form onSubmit={handleSubmit} className="space-y-4">
        <AuthField htmlFor="full_name" label={t(keys.users.common.full_name)}>
          <Input
            id="full_name"
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder={t(keys.users.common.name_placeholder)}
            autoComplete="name"
          />
        </AuthField>
        <PasswordFields
          password={password}
          onPasswordChange={(next) => {
            setPassword(next);
            setMismatch(false);
          }}
          confirm={confirm}
          onConfirmChange={(next) => {
            setConfirm(next);
            setMismatch(false);
          }}
          passwordLabel={t(keys.users.common.password)}
          confirmLabel={t(keys.users.common.confirm_password)}
          mismatch={mismatch}
          hint={t(keys.users.common.password_hint)}
        />

        {error && <p className="text-sm text-destructive">{error}</p>}

        <Button
          type="submit"
          size="lg"
          className="w-full max-lg:min-h-11"
          disabled={loading || !token}
        >
          {loading ? t(keys.users.accept_invite.submitting) : t(keys.users.accept_invite.submit)}
        </Button>
      </form>
      <p className="mt-4 text-center text-[12.5px] leading-relaxed text-muted-foreground">
        {t(keys.users.accept_invite.helper)}
      </p>
    </AuthCardShell>
  );
}

export default AcceptInvite;
