import { Head } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { AuthCardShell } from '@simple-module-py/ui/layouts/AuthCardShell';
import { apiFetch, NETWORK_FAILURE } from '@simple-module-py/ui/lib/api';
import { LOGIN_PATH } from '@simple-module-py/ui/lib/auth-routes';
import { MailCheck, UserCheck } from 'lucide-react';
import { useState } from 'react';
import { AuthField } from '../auth_local/components/AuthField';
import { AuthIntro } from '../auth_local/components/AuthIntro';
import { AuthStateCard } from '../auth_local/components/AuthStateCard';
import { PasswordFields } from '../auth_local/components/PasswordFields';
import {
  FAILED,
  livePasswordIssue,
  mapRegisterError,
  passwordPolicyIssue,
  type RegisterError,
  type RegisterErrorCode,
} from '../auth_local/registerErrors';

interface RegisterProps {
  /** `users.require_verification`: whether a new account must confirm its email. */
  require_verification?: boolean;
}

function Register({ require_verification = true }: RegisterProps) {
  const { t } = useT();
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [mismatch, setMismatch] = useState(false);
  const [error, setError] = useState<RegisterError | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);
  // Everything that differs between "check your inbox" and "you can sign in now".
  const copy = require_verification
    ? {
        icon: MailCheck,
        title: keys.users.register.success_title,
        body: keys.users.register.success_body,
        bullet: keys.users.register.bullet_verification,
      }
    : {
        icon: UserCheck,
        title: keys.users.register.success_ready_title,
        body: keys.users.register.success_ready_body,
        bullet: keys.users.register.bullet_no_verification,
      };

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
  const policyIssue = passwordPolicyIssue(password, email);
  const policyOk = policyIssue === null;
  const liveIssue = livePasswordIssue(password, email);
  const passwordError = errorFor('password') ?? (liveIssue ? message(liveIssue) : null);
  // A server error describes the value that was sent; once that field is
  // edited it no longer applies.
  const clearErrorOn = (field: RegisterError['field']) => {
    if (error?.field === field) setError(null);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (policyIssue) {
      setError({ field: 'password', code: policyIssue });
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
    // Untyped on purpose: the generated `UserCreate` demands the privileged
    // `is_active`/`is_superuser`/`is_verified` keys, which a sign-up must not send.
    apiFetch('/api/users/auth/register', {
      method: 'POST',
      json: { email, password, full_name: fullName },
    })
      .then((res) => {
        if (res.status === 201) {
          setSuccess(true);
        } else if (res.status === NETWORK_FAILURE) {
          setError(FAILED);
        } else {
          setError(mapRegisterError(res.error ?? {}));
        }
      })
      .finally(() => setLoading(false));
  };

  if (success) {
    return (
      <AuthCardShell>
        <Head title={t(keys.users.register.head_title)} />
        <AuthStateCard
          icon={copy.icon}
          tone="primary"
          title={t(copy.title)}
          description={t(copy.body, { email })}
        >
          <Button asChild className="max-lg:min-h-11">
            <a href={LOGIN_PATH}>{t(keys.users.common.sign_in)}</a>
          </Button>
        </AuthStateCard>
      </AuthCardShell>
    );
  }

  // A host can hide the entire reassurance by overriding this catalog key to empty.
  const registrationNote = t(keys.users.register.bullet_close).trim();
  const intro = (
    <AuthIntro
      heading={t(keys.users.register.heading)}
      body={t(keys.users.register.intro)}
      checks={[t(copy.bullet), ...(registrationNote ? [registrationNote] : [])]}
    />
  );

  return (
    <AuthCardShell variant="split-light" aside={intro} width="lg">
      <Head title={t(keys.users.register.head_title)} />
      {/* noValidate: the browser's bubble is in the browser's language and
          sets no aria-invalid; the server's 422 maps to a translated field error. */}
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
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
            onChange={(e) => {
              setEmail(e.target.value);
              clearErrorOn('email');
              // "contains your email" is about the pair, so editing either side voids it.
              if (error?.code === 'password_contains_email') setError(null);
            }}
            placeholder={t(keys.users.common.email_placeholder)}
            required
            autoComplete="email"
            aria-invalid={errorFor('email') ? true : undefined}
          />
        </AuthField>
        <PasswordFields
          password={password}
          onPasswordChange={(next) => {
            setPassword(next);
            setMismatch(false);
            clearErrorOn('password');
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
          passwordError={passwordError}
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
