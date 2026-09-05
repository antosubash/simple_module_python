import { Head, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { AuthCardShell } from '@simple-module-py/ui/layouts/AuthCardShell';
import { LOGIN_PATH } from '@simple-module-py/ui/lib/auth-routes';
import { useState } from 'react';
import { AuthField } from '../auth_local/components/AuthField';
import { ResetLinkSent } from '../auth_local/components/ResetLinkSent';

interface Props {
  /** How long the emailed link stays usable — straight from settings. */
  reset_link_lifetime_minutes: number;
  /** False for the console mailer, which only writes the link to the log. */
  mailer_delivers: boolean;
}

function ForgotPassword() {
  const { reset_link_lifetime_minutes, mailer_delivers } = usePage<{ props: Props }>()
    .props as unknown as Props;
  const { t } = useT();
  const [email, setEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  /** Resolves to whether the server took the request — never rejects. */
  const requestLink = (): Promise<boolean> =>
    fetch('/api/users/auth/forgot-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    })
      .then((res) => res.ok)
      .catch(() => false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    requestLink().finally(() => {
      // Anti-enumeration: always show the same confirmation regardless of
      // whether the email exists (fastapi-users returns 202 either way). The
      // outcome is deliberately ignored *here* — the sent card is the answer
      // to "does this address have an account", and it must not vary. A
      // refusal only surfaces on the explicit resend, which is about this
      // request rather than about the address.
      setLoading(false);
      setSubmitted(true);
    });
  };

  if (submitted) {
    return (
      <AuthCardShell>
        <Head title={t(keys.users.forgot_password.head_title)} />
        <ResetLinkSent email={email} mailerDelivers={mailer_delivers} onResend={requestLink} />
        <a
          href={LOGIN_PATH}
          className="mt-6 block text-center text-[13px] font-medium text-primary-700 hover:text-primary-800"
        >
          {t(keys.users.common.back_to_sign_in)}
        </a>
      </AuthCardShell>
    );
  }

  return (
    <AuthCardShell>
      <Head title={t(keys.users.forgot_password.head_title)} />
      <h1 className="text-[21px] font-bold tracking-tight text-foreground font-display">
        {t(keys.users.forgot_password.heading)}
      </h1>
      <p className="mt-2 mb-5 text-sm leading-relaxed text-muted-foreground">
        {t(keys.users.forgot_password.subtitle, { minutes: reset_link_lifetime_minutes })}
      </p>
      <form onSubmit={handleSubmit} className="space-y-4">
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
        <Button type="submit" size="lg" className="w-full" disabled={loading}>
          {loading
            ? t(keys.users.forgot_password.submitting)
            : t(keys.users.forgot_password.submit)}
        </Button>
      </form>
      <a
        href={LOGIN_PATH}
        className="mt-5 block text-center text-[13px] font-medium text-primary-700 hover:text-primary-800"
      >
        {t(keys.users.common.back_to_sign_in)}
      </a>
    </AuthCardShell>
  );
}

export default ForgotPassword;
