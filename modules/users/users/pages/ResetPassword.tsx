import { Head, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { AuthCardShell } from '@simple-module-py/ui/layouts/AuthCardShell';
import { LOGIN_PATH } from '@simple-module-py/ui/lib/auth-routes';
import { useState } from 'react';

interface Props {
  token: string;
}

function ResetPassword() {
  const { token: initialToken } = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();

  const urlToken =
    typeof window !== 'undefined'
      ? (new URLSearchParams(window.location.search).get('token') ?? '')
      : '';
  const token = urlToken || initialToken;

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError(t(keys.users.common.passwords_no_match));
      return;
    }
    setLoading(true);
    fetch('/api/users/auth/reset-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, password }),
    })
      .then(async (res) => {
        if (res.status === 200 || res.status === 204) {
          router.visit(LOGIN_PATH);
        } else {
          const data = await res.json().catch(() => ({}));
          const detail =
            typeof data?.detail === 'string'
              ? data.detail
              : t(keys.users.reset_password.error_failed);
          setError(detail);
        }
      })
      .catch(() => setError(t(keys.users.common.error_try_again)))
      .finally(() => setLoading(false));
  };

  return (
    <AuthCardShell>
      <Head title={t(keys.users.reset_password.head_title)} />
      <h1 className="mb-1.5 text-[22px] font-bold tracking-tight font-[var(--font-display)] text-foreground">
        {t(keys.users.reset_password.heading)}
      </h1>
      <p className="mb-5 text-sm text-muted-foreground">{t(keys.users.reset_password.subtitle)}</p>
      <form onSubmit={handleSubmit} className="space-y-3.5">
        <div className="space-y-1.5">
          <Label htmlFor="password" className="text-sm font-medium text-muted-foreground">
            {t(keys.users.common.new_password)}
          </Label>
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={t(keys.users.common.password_placeholder)}
            required
            autoComplete="new-password"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="confirm" className="text-sm font-medium text-muted-foreground">
            {t(keys.users.common.confirm_password)}
          </Label>
          <Input
            id="confirm"
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            autoComplete="new-password"
          />
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <Button type="submit" size="lg" className="w-full" disabled={loading || !token}>
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
