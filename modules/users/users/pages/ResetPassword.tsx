import { Head, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { AuthCardShell } from '@simple-module-py/ui/layouts/AuthCardShell';
import { LOGIN_PATH } from '@simple-module-py/ui/lib/auth-routes';
import { CheckCircle2, TimerOff } from 'lucide-react';
import { useState } from 'react';
import { AuthStateCard } from '../auth_local/components/AuthStateCard';
import { PasswordFields } from '../auth_local/components/PasswordFields';

const FORGOT_PATH = '/users/forgot-password';
const DASHBOARD_PATH = '/dashboard/';

interface Props {
  token: string;
  /** The address the token was issued for — signs the reset in when it lands. */
  email: string | null;
  /** True when a token was supplied and could not be read. */
  expired: boolean;
  reset_link_lifetime_minutes: number;
}

function ResetPassword() {
  const {
    token,
    email,
    expired,
    reset_link_lifetime_minutes: lifetimeMinutes,
  } = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [mismatch, setMismatch] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saved, setSaved] = useState(false);

  /** Sign in with the address the token named, so "Save and sign in" is one step.
   *
   * Never rejects: by the time this runs the password has already been
   * changed, and a network error here must not be reported as a failed reset. */
  const signIn = async () => {
    if (!email) return false;
    try {
      const res = await fetch('/api/users/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ username: email, password }),
      });
      return res.status === 204;
    } catch {
      return false;
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setMismatch(true);
      return;
    }
    setMismatch(false);
    setLoading(true);
    fetch('/api/users/auth/reset-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, password }),
    })
      .then(async (res) => {
        if (res.status !== 200 && res.status !== 204) {
          const data = await res.json().catch(() => ({}));
          setError(
            typeof data?.detail === 'string'
              ? data.detail
              : t(keys.users.reset_password.error_failed),
          );
          return;
        }
        if (await signIn()) {
          router.visit(DASHBOARD_PATH);
          return;
        }
        // The password *was* saved — the reset returned 200. Reporting a
        // generic failure here would send someone back to try the dead link
        // again with the old password. Say what actually happened and hand
        // them the sign-in page.
        setSaved(true);
      })
      .catch(() => setError(t(keys.users.common.error_try_again)))
      .finally(() => setLoading(false));
  };

  if (saved) {
    return (
      <AuthCardShell>
        <Head title={t(keys.users.reset_password.head_title)} />
        <AuthStateCard
          icon={CheckCircle2}
          tone="primary"
          title={t(keys.users.reset_password.saved_title)}
          description={t(keys.users.reset_password.saved_description)}
        >
          <Button asChild className="max-lg:min-h-11">
            <a href={LOGIN_PATH}>{t(keys.users.common.sign_in)}</a>
          </Button>
        </AuthStateCard>
      </AuthCardShell>
    );
  }

  if (expired) {
    return (
      <AuthCardShell tone="destructive">
        <Head title={t(keys.users.reset_password.head_title)} />
        <AuthStateCard
          icon={TimerOff}
          tone="destructive"
          title={t(keys.users.reset_password.expired_title)}
          description={t(keys.users.reset_password.expired_body, { minutes: lifetimeMinutes })}
        >
          <Button asChild className="max-lg:min-h-11">
            <a href={FORGOT_PATH}>{t(keys.users.reset_password.expired_action)}</a>
          </Button>
        </AuthStateCard>
      </AuthCardShell>
    );
  }

  return (
    <AuthCardShell>
      <Head title={t(keys.users.reset_password.head_title)} />
      <h1 className="mb-5 text-[21px] font-bold tracking-tight text-foreground font-display">
        {t(keys.users.reset_password.heading)}
      </h1>
      <form onSubmit={handleSubmit} className="space-y-4">
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
          passwordLabel={t(keys.users.common.new_password)}
          confirmLabel={t(keys.users.reset_password.confirm_label)}
          mismatch={mismatch}
        />

        {error && <p className="text-sm text-destructive">{error}</p>}

        <Button
          type="submit"
          size="lg"
          className="w-full max-lg:min-h-11"
          disabled={loading || !token}
        >
          {loading ? t(keys.users.reset_password.submitting) : t(keys.users.reset_password.submit)}
        </Button>
      </form>
      {!token && (
        <p className="mt-3 text-sm text-destructive">{t(keys.users.reset_password.no_token)}</p>
      )}
    </AuthCardShell>
  );
}

export default ResetPassword;
