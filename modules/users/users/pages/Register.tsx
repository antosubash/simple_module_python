import { Head } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { AuthCardShell } from '@simple-module-py/ui/layouts/AuthCardShell';
import { LOGIN_PATH } from '@simple-module-py/ui/lib/auth-routes';
import { MailCheck } from 'lucide-react';
import { useState } from 'react';
import { AuthField } from '../auth_local/components/AuthField';
import { AuthIntro } from '../auth_local/components/AuthIntro';
import { AuthStateCard } from '../auth_local/components/AuthStateCard';
import { PasswordFields } from '../auth_local/components/PasswordFields';

function Register() {
  const { t } = useT();
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [mismatch, setMismatch] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      // Field-level, not a line under the whole form: the error belongs to
      // the box that caused it.
      setMismatch(true);
      return;
    }
    setMismatch(false);
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
        <Head title={t(keys.users.register.head_title)} />
        <AuthStateCard
          icon={MailCheck}
          tone="primary"
          title={t(keys.users.register.success_title)}
          description={t(keys.users.register.success_body, { email })}
        >
          <Button asChild className="max-lg:min-h-11">
            <a href={LOGIN_PATH}>{t(keys.users.common.sign_in)}</a>
          </Button>
        </AuthStateCard>
      </AuthCardShell>
    );
  }

  const intro = (
    <AuthIntro
      heading={t(keys.users.register.heading)}
      body={t(keys.users.register.intro)}
      checks={[
        t(keys.users.register.bullet_verification),
        <>
          {t(keys.users.register.bullet_close_prefix)}{' '}
          <code className="font-mono text-[12.5px]">users.allow_signup</code>
        </>,
      ]}
    />
  );

  return (
    <AuthCardShell variant="split-light" aside={intro} width="lg">
      <Head title={t(keys.users.register.head_title)} />
      <form onSubmit={handleSubmit} className="space-y-4">
        <AuthField htmlFor="full_name" label={t(keys.users.common.full_name)}>
          <Input
            id="full_name"
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder={t(keys.users.register.name_placeholder)}
            autoComplete="name"
          />
        </AuthField>
        <AuthField htmlFor="email" label={t(keys.users.common.email)}>
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t(keys.users.common.email_placeholder)}
            required
            autoComplete="email"
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

        <Button type="submit" size="lg" className="w-full" disabled={loading}>
          {loading ? t(keys.users.register.submitting) : t(keys.users.register.submit)}
        </Button>
      </form>

      <p className="mt-5 text-center text-[13.5px] text-muted-foreground">
        {t(keys.users.register.have_account)}{' '}
        <a href={LOGIN_PATH} className="font-medium text-primary-700 hover:text-primary-800">
          {t(keys.users.common.sign_in)}
        </a>
      </p>
    </AuthCardShell>
  );
}

export default Register;
