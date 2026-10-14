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
import {
  mapRegisterError,
  meetsPasswordPolicy,
  type RegisterError,
  type RegisterErrorCode,
} from '../auth_local/registerErrors';

function Register() {
  const { t } = useT();
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [mismatch, setMismatch] = useState(false);
  const [error, setError] = useState<RegisterError | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const message = (code: RegisterErrorCode) => {
    const r = keys.users.register;
    const byCode = {
      exists: r.error_exists,
      email_invalid: r.error_email_invalid,
      password_length: r.error_password_length,
      password_contains_email: r.error_password_contains_email,
      password_numeric: r.error_password_numeric,
      password_invalid: r.error_password_invalid,
      failed: r.error_failed,
    } as const;
    return t(byCode[code]);
  };
  const errorFor = (field: RegisterError['field']) =>
    error?.field === field ? message(error.code) : null;
  // The server's own password policy, not the meter: "ok" and "weak" are
  // feedback, but a password the API will refuse is not worth a round trip.
  const policyOk = meetsPasswordPolicy(password, email);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!policyOk) {
      setError({ field: 'password', code: 'password_invalid' });
      return;
    }
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
          setError(mapRegisterError(await res.json().catch(() => ({}))));
        }
      })
      .catch(() => setError({ field: 'form', code: 'failed' }))
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
        <AuthField htmlFor="email" label={t(keys.users.common.email)} error={errorFor('email')}>
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t(keys.users.common.email_placeholder)}
            required
            autoComplete="email"
            aria-invalid={error?.field === 'email' ? true : undefined}
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
          passwordError={errorFor('password')}
        />

        {error?.field === 'form' && (
          <p className="text-sm text-destructive">{message(error.code)}</p>
        )}

        <Button type="submit" size="lg" className="w-full" disabled={loading || !policyOk}>
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
