import { Head } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { AuthCardShell } from '@simple-module-py/ui/layouts/AuthCardShell';
import { LOGIN_PATH } from '@simple-module-py/ui/lib/auth-routes';
import { CheckCircle2 } from 'lucide-react';
import { useState } from 'react';

function ForgotPassword() {
  const { t } = useT();
  const [email, setEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    fetch('/api/users/auth/forgot-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    }).finally(() => {
      // Anti-enumeration: always show the same confirmation regardless of
      // whether the email exists (fastapi-users returns 202 either way).
      setLoading(false);
      setSubmitted(true);
    });
  };

  if (submitted) {
    return (
      <AuthCardShell>
        <div className="flex items-start gap-3 rounded-xl border border-primary-200 bg-primary-50 p-3 text-sm text-primary-800">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <div>
            <p className="font-semibold">{t(keys.users.forgot_password.sent_title)}</p>
            <p className="mt-0.5">{t(keys.users.forgot_password.sent_body, { email })}</p>
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
      <Head title={t(keys.users.forgot_password.head_title)} />
      <h1 className="mb-1.5 text-[22px] font-bold tracking-tight font-[var(--font-display)] text-foreground">
        {t(keys.users.forgot_password.heading)}
      </h1>
      <p className="mb-5 text-sm text-muted-foreground">{t(keys.users.forgot_password.subtitle)}</p>
      <form onSubmit={handleSubmit} className="space-y-3.5">
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
        <Button type="submit" size="lg" className="w-full" disabled={loading}>
          {loading
            ? t(keys.users.forgot_password.submitting)
            : t(keys.users.forgot_password.submit)}
        </Button>
      </form>
      <p className="mt-5 text-center text-xs text-muted-foreground">
        {t(keys.users.forgot_password.remembered)}{' '}
        <a href={LOGIN_PATH} className="font-semibold text-primary-700 hover:text-primary-800">
          {t(keys.users.common.log_in)}
        </a>
      </p>
    </AuthCardShell>
  );
}

export default ForgotPassword;
