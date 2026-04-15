import { router, usePage } from '@inertiajs/react';
import { Button } from '@simple-module/ui/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@simple-module/ui/components/ui/card';
import { Input } from '@simple-module/ui/components/ui/input';
import { Label } from '@simple-module/ui/components/ui/label';
import { useState } from 'react';

interface Props {
  token: string;
}

function ResetPassword() {
  const { token: initialToken } = usePage<{ props: Props }>().props as unknown as Props;

  // Prefer the token from the URL query string (deeplink); fall back to Inertia prop.
  const urlToken =
    typeof window !== 'undefined'
      ? new URLSearchParams(window.location.search).get('token') ?? ''
      : '';
  const token = urlToken || initialToken;

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setLoading(true);
    fetch('/api/users/auth/reset-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, password }),
    })
      .then(async (res) => {
        if (res.status === 200 || res.status === 204) {
          router.visit('/users/login');
        } else {
          const data = await res.json().catch(() => ({}));
          const detail = typeof data?.detail === 'string' ? data.detail : 'Reset failed. The link may have expired.';
          setError(detail);
        }
      })
      .catch(() => setError('An error occurred. Please try again.'))
      .finally(() => setLoading(false));
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-muted p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl">Reset password</CardTitle>
          <CardDescription>Choose a new password for your account</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="password">New password</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="new-password"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirm">Confirm password</Label>
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

            <Button type="submit" className="w-full" disabled={loading || !token}>
              {loading ? 'Resetting…' : 'Reset password'}
            </Button>
          </form>
          {!token && (
            <p className="mt-2 text-sm text-destructive">
              No reset token found. Please use the link from your email.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default ResetPassword;
