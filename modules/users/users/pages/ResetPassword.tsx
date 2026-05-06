import { router, usePage } from '@inertiajs/react';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { AuthCardShell } from '@simple-module-py/ui/layouts/AuthCardShell';
import { useState } from 'react';

interface Props {
  token: string;
}

function ResetPassword() {
  const { token: initialToken } = usePage<{ props: Props }>().props as unknown as Props;

  const urlToken =
    typeof window !== 'undefined'
      ? (new URLSearchParams(window.location.search).get('token') ?? '')
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
          const detail =
            typeof data?.detail === 'string'
              ? data.detail
              : 'Reset failed. The link may have expired.';
          setError(detail);
        }
      })
      .catch(() => setError('An error occurred. Please try again.'))
      .finally(() => setLoading(false));
  };

  return (
    <AuthCardShell>
      <h1 className="mb-1.5 text-[22px] font-bold tracking-tight font-[var(--font-display)] text-foreground">
        Reset password
      </h1>
      <p className="mb-5 text-sm text-muted-foreground">
        Choose a new password and you'll be redirected to log in.
      </p>
      <form onSubmit={handleSubmit} className="space-y-3.5">
        <div className="space-y-1.5">
          <Label htmlFor="password" className="text-sm font-medium text-muted-foreground">
            New password
          </Label>
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="8+ characters"
            required
            autoComplete="new-password"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="confirm" className="text-sm font-medium text-muted-foreground">
            Confirm password
          </Label>
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

        <Button type="submit" size="lg" className="w-full" disabled={loading || !token}>
          {loading ? 'Resetting…' : 'Reset password'}
        </Button>
      </form>
      {!token && (
        <p className="mt-3 text-sm text-destructive">
          No reset token found. Please use the link from your email.
        </p>
      )}
    </AuthCardShell>
  );
}

export default ResetPassword;
