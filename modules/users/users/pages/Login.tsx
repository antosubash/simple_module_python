import { router, usePage } from '@inertiajs/react';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { AuthCardShell } from '@simple-module-py/ui/layouts/AuthCardShell';
import { useState } from 'react';

interface DevAccount {
  label: string;
  email: string;
  password: string;
}

interface Props {
  allow_signup: boolean;
  dev_accounts: DevAccount[];
  login_redirect_url: string;
}

function Login() {
  const { allow_signup, dev_accounts, login_redirect_url } = usePage<{ props: Props }>()
    .props as unknown as Props;

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [needsVerification, setNeedsVerification] = useState(false);
  const [loading, setLoading] = useState(false);

  const nextUrl =
    typeof window !== 'undefined'
      ? new URLSearchParams(window.location.search).get('next') || login_redirect_url
      : login_redirect_url;

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
          setError('Too many attempts. Please try again in a few minutes.');
        } else {
          const data = await res.json().catch(() => ({}));
          const detail = typeof data?.detail === 'string' ? data.detail : '';
          if (detail === 'LOGIN_USER_NOT_VERIFIED') {
            setNeedsVerification(true);
          } else {
            setError('Invalid email or password.');
          }
        }
      })
      .catch(() => setError('An error occurred. Please try again.'))
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
      setError('Verification email resent. Please check your inbox.');
      setNeedsVerification(false);
    });
  };

  return (
    <AuthCardShell>
      <h1 className="text-2xl font-semibold tracking-tight">Welcome back</h1>
      <p className="mb-6 mt-1 text-sm text-muted-foreground">
        Sign in to continue your validation work.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="email" className="text-xs font-medium">
            Email
          </Label>
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@institution.org"
            required
            autoComplete="email"
          />
        </div>
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label htmlFor="password" className="text-xs font-medium">
              Password
            </Label>
            <a
              href="/users/forgot-password"
              className="text-[11px] text-primary-700 hover:underline"
            >
              Forgot?
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

        {error && <p className="text-xs text-destructive">{error}</p>}

        {needsVerification && (
          <div className="rounded border border-amber-300 bg-amber-50 p-3 text-xs text-amber-800">
            <p>Please verify your email before signing in.</p>
            <button
              type="button"
              onClick={handleResendVerification}
              className="mt-1 underline hover:no-underline"
            >
              Resend verification email
            </button>
          </div>
        )}

        <Button type="submit" className="w-full" disabled={loading}>
          {loading ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>

      <div className="my-5 flex items-center gap-3 font-mono text-[11px] text-muted-foreground">
        <span className="h-px flex-1 bg-border" />
        OR
        <span className="h-px flex-1 bg-border" />
      </div>

      {allow_signup && (
        <a
          href="/users/register"
          className="inline-flex w-full items-center justify-center rounded border border-border bg-card px-3 py-2 text-xs font-medium hover:border-primary-400"
        >
          Create an account
        </a>
      )}

      {dev_accounts && dev_accounts.length > 0 && (
        <div className="mt-6 border-t border-border/60 pt-4">
          <p className="mb-2 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            Dev quick-login
          </p>
          <div className="flex flex-wrap gap-2">
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
                  submitLogin(acct.email, acct.password);
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
