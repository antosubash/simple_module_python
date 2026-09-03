import { Head, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { AuthCardShell } from '@simple-module-py/ui/layouts/AuthCardShell';
import { AuthSplitAside } from '@simple-module-py/ui/layouts/AuthSplitAside';
import { useState } from 'react';
import { LoginForm, type OAuthProvider } from '../auth_local/components/LoginForm';
import { WaitingOnYou } from '../auth_local/components/WaitingOnYou';

interface DevAccount {
  label: string;
  email: string;
  password: string;
}

interface Props {
  allow_signup: boolean;
  dev_accounts: DevAccount[];
  login_redirect_url: string;
  oauth_providers: OAuthProvider[];
  remember_me_days: number;
}

function Login() {
  const { allow_signup, dev_accounts, login_redirect_url, oauth_providers, remember_me_days } =
    usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsVerification, setNeedsVerification] = useState(false);
  const [resent, setResent] = useState(false);
  const [loading, setLoading] = useState(false);

  // Server-decided, deliberately. The post-login destination used to be read
  // from `?next=` here, which let any crafted login link bounce the user to an
  // arbitrary URL after signing in. AuthMiddleware now stashes the target in
  // the session and the view sanitises it, so this prop is already safe.
  const nextUrl = login_redirect_url;

  const submitLogin = (username: string, pwd: string) => {
    setError(null);
    setNeedsVerification(false);
    setLoading(true);
    const body = new URLSearchParams({
      username,
      password: pwd,
      remember: String(remember),
    });
    fetch('/api/users/auth/login', {
      method: 'POST',
      body,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
      .then(async (res) => {
        if (res.status === 204) {
          router.visit(nextUrl);
        } else if (res.status === 429) {
          setError(t(keys.users.login.error_rate_limited));
        } else {
          const data = await res.json().catch(() => ({}));
          const detail = typeof data?.detail === 'string' ? data.detail : '';
          if (detail === 'LOGIN_USER_NOT_VERIFIED') {
            setNeedsVerification(true);
          } else {
            setError(t(keys.users.login.error_invalid_credentials));
          }
        }
      })
      .catch(() => setError(t(keys.users.common.error_try_again)))
      .finally(() => setLoading(false));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submitLogin(email, password);
  };

  const handleResendVerification = () => {
    fetch('/api/users/auth/request-verify-token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    }).then(() => setResent(true));
  };

  const aside = (
    <AuthSplitAside
      heading={t(keys.users.login.aside_heading)}
      body={t(keys.users.login.aside_body)}
      checks={[t(keys.users.login.aside_check_sessions), t(keys.users.login.aside_check_sso)]}
    />
  );

  return (
    <AuthCardShell variant="split-dark" aside={aside}>
      <Head title={t(keys.users.login.head_title)} />
      {needsVerification ? (
        <WaitingOnYou
          email={email}
          resent={resent}
          onResend={handleResendVerification}
          onBack={() => {
            setNeedsVerification(false);
            setResent(false);
          }}
        />
      ) : (
        <LoginForm
          email={email}
          onEmailChange={setEmail}
          password={password}
          onPasswordChange={setPassword}
          remember={remember}
          onRememberChange={setRemember}
          rememberDays={remember_me_days}
          error={error}
          loading={loading}
          onSubmit={handleSubmit}
          allowSignup={allow_signup}
          oauthProviders={oauth_providers ?? []}
        />
      )}

      {dev_accounts && dev_accounts.length > 0 && !needsVerification && (
        <div className="mt-5 border-t border-border pt-4">
          <p className="mb-2 text-center font-mono text-[11px] text-muted-foreground">
            {t(keys.users.login.dev_divider)}
          </p>
          <div className="flex flex-wrap justify-center gap-2">
            {dev_accounts.map((acct) => (
              <Button
                key={acct.email}
                type="button"
                variant="outline"
                size="sm"
                disabled={loading}
                onClick={() => {
                  setEmail(acct.email);
                  setPassword(acct.password);
                }}
              >
                {acct.label}
              </Button>
            ))}
          </div>
        </div>
      )}
    </AuthCardShell>
  );
}

export default Login;
