import { router, usePage } from '@inertiajs/react';
import { Button } from '@simple-module/ui/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@simple-module/ui/components/ui/card';
import { Input } from '@simple-module/ui/components/ui/input';
import { Label } from '@simple-module/ui/components/ui/label';
import { AuthCardShell } from '@simple-module/ui/layouts/AuthCardShell';
import { useState } from 'react';

interface Props {
  allow_signup: boolean;
}

function Login() {
  const { allow_signup } = usePage<{ props: Props }>().props as unknown as Props;

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [needsVerification, setNeedsVerification] = useState(false);
  const [loading, setLoading] = useState(false);

  const nextUrl = typeof window !== 'undefined'
    ? new URLSearchParams(window.location.search).get('next') || '/dashboard'
    : '/dashboard';

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setNeedsVerification(false);
    setLoading(true);
    const body = new URLSearchParams({ username: email, password });
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
      <Card className="w-full max-w-sm">
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl">Sign in</CardTitle>
          <CardDescription>Enter your email and password to continue</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
                autoComplete="email"
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="password">Password</Label>
                <a href="/users/forgot-password" className="text-sm text-primary hover:underline">
                  Forgot password?
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
              <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
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

          {allow_signup && (
            <p className="mt-4 text-center text-sm text-muted-foreground">
              Don't have an account?{' '}
              <a href="/users/register" className="text-primary hover:underline">
                Create account
              </a>
            </p>
          )}
        </CardContent>
      </Card>
    </AuthCardShell>
  );
}

export default Login;
