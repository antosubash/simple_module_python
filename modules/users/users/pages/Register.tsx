import { Head } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { AuthCardShell } from '@simple-module-py/ui/layouts/AuthCardShell';
import { LOGIN_PATH } from '@simple-module-py/ui/lib/auth-routes';
import { CheckCircle2 } from 'lucide-react';
import { useState } from 'react';

function Register() {
  const { t } = useT();
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError(t(keys.users.common.passwords_no_match));
      return;
    }
    setLoading(true);
    fetch('/api/users/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, full_name: fullName }),
    })
      .then(async (res) => {
        if (res.status === 201) {
          setSuccess(true);
        } else {
          const data = await res.json().catch(() => ({}));
          const detail = data?.detail;
          if (detail === 'REGISTER_USER_ALREADY_EXISTS') {
            setError(t(keys.users.register.error_exists));
          } else if (typeof detail === 'object' && detail?.code === 'REGISTER_INVALID_PASSWORD') {
            setError(
              t(keys.users.register.error_weak_password, {
                reason: detail.reason ?? t(keys.users.register.error_weak_password_default),
              }),
            );
          } else if (typeof detail === 'string') {
            setError(detail);
          } else {
            setError(t(keys.users.register.error_failed));
          }
        }
      })
      .catch(() => setError(t(keys.users.common.error_try_again)))
      .finally(() => setLoading(false));
  };

  if (success) {
    return (
      <AuthCardShell>
        <div className="flex items-start gap-3 rounded-xl border border-primary-200 bg-primary-50 p-3 text-sm text-primary-800">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <div>
            <p className="font-semibold">{t(keys.users.register.success_title)}</p>
            <p className="mt-0.5">{t(keys.users.register.success_body, { email })}</p>
          </div>
        </div>
        <a
          href={LOGIN_PATH}
          className="mt-4 block text-center text-sm font-semibold text-primary-700 hover:text-primary-800"
        >
          {t(keys.users.common.back_to_login)}
        </a>
      </AuthCardShell>
    );
  }

  return (
    <AuthCardShell>
      <Head title={t(keys.users.register.head_title)} />
      <h1 className="mb-1.5 text-[22px] font-bold tracking-tight font-[var(--font-display)] text-foreground">
        {t(keys.users.register.heading)}
      </h1>
      <p className="mb-5 text-sm text-muted-foreground">
        {t(keys.users.register.subtitle_prefix)}{' '}
        <code className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[12px]">
          SM_USERS_ALLOW_SIGNUP
        </code>
        .
      </p>
      <form onSubmit={handleSubmit} className="space-y-3.5">
        <div className="space-y-1.5">
          <Label htmlFor="full_name" className="text-sm font-medium text-muted-foreground">
            {t(keys.users.common.full_name)}
          </Label>
          <Input
            id="full_name"
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder={t(keys.users.common.name_placeholder)}
            autoComplete="name"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="email" className="text-sm font-medium text-muted-foreground">
            {t(keys.users.common.email)}
          </Label>
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t(keys.users.common.email_placeholder)}
            required
            autoComplete="email"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="password" className="text-sm font-medium text-muted-foreground">
            {t(keys.users.common.password)}
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

        <Button type="submit" size="lg" className="w-full" disabled={loading}>
          {loading ? t(keys.users.register.submitting) : t(keys.users.register.submit)}
        </Button>
      </form>

      <p className="mt-5 text-center text-xs text-muted-foreground">
        {t(keys.users.register.have_account)}{' '}
        <a href={LOGIN_PATH} className="font-semibold text-primary-700 hover:text-primary-800">
          {t(keys.users.common.log_in)}
        </a>
      </p>
    </AuthCardShell>
  );
}

export default Register;
