import { Head, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { AuthCardShell } from '@simple-module-py/ui/layouts/AuthCardShell';
import { REGISTER_PATH } from '@simple-module-py/ui/lib/auth-routes';
import { AlertTriangle } from 'lucide-react';
import { useState } from 'react';

interface DevAccount {
  label: string;
  email: string;
  password: string;
}

interface OAuthProvider {
  name: string;
  display_name: string;
}

interface Props {
  allow_signup: boolean;
  dev_accounts: DevAccount[];
  login_redirect_url: string;
  oauth_providers: OAuthProvider[];
}

function Login() {
  const { allow_signup, dev_accounts, login_redirect_url, oauth_providers } = usePage<{
    props: Props;
  }>().props as unknown as Props;
  const { t } = useT();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [needsVerification, setNeedsVerification] = useState(false);
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
    const body = new URLSearchParams({ username, password: pwd });
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
    }).then(() => {
      setError(t(keys.users.login.verification_resent));
      setNeedsVerification(false);
    });
  };

  return (
    <AuthCardShell>
      <Head title={t(keys.users.login.head_title)} />
      <h1 className="mb-1.5 text-[22px] font-bold tracking-tight font-[var(--font-display)] text-foreground">
        {t(keys.users.login.heading)}
      </h1>
      <p className="mb-5 text-sm text-muted-foreground">{t(keys.users.login.subtitle)}</p>
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
        <div className="space-y-1.5">
          <div className="flex items-baseline justify-between">
            <Label htmlFor="password" className="text-sm font-medium text-muted-foreground">
              {t(keys.users.common.password)}
            </Label>
            <a
              href="/users/forgot-password"
              className="text-xs font-semibold text-primary-700 hover:text-primary-800"
            >
              {t(keys.users.login.forgot_link)}
            </a>
          </div>
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
          />
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        {needsVerification && (
          <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <div>
              <p className="font-semibold">{t(keys.users.login.needs_verification_title)}</p>
              <button
                type="button"
                onClick={handleResendVerification}
                className="mt-0.5 underline hover:no-underline"
              >
                {t(keys.users.login.resend_verification)}
              </button>
            </div>
          </div>
        )}

        <Button type="submit" size="lg" className="w-full" disabled={loading}>
          {loading ? t(keys.users.login.submitting) : t(keys.users.login.submit)}
        </Button>
      </form>

      {allow_signup && (
        <p className="mt-5 text-center text-xs text-muted-foreground">
          {t(keys.users.login.no_account)}{' '}
          <a href={REGISTER_PATH} className="font-semibold text-primary-700 hover:text-primary-800">
            {t(keys.users.login.sign_up)}
          </a>
        </p>
      )}

      {oauth_providers && oauth_providers.length > 0 && (
        <div className="mt-5 border-t border-border pt-4">
          <p className="mb-2 text-center font-mono text-[11px] text-muted-foreground">
            {t(keys.users.login.oauth_divider)}
          </p>
          <div className="flex flex-col gap-2">
            {oauth_providers.map((p) => (
              <Button key={p.name} type="button" variant="outline" asChild disabled={loading}>
                <a href={`/api/users/auth/${p.name}/login`}>{p.display_name}</a>
              </Button>
            ))}
          </div>
        </div>
      )}

      {dev_accounts && dev_accounts.length > 0 && (
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
