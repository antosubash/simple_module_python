import { router, usePage } from '@inertiajs/react';
import { Button } from '@simple-module/ui/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@simple-module/ui/components/ui/card';
import { Input } from '@simple-module/ui/components/ui/input';
import { Label } from '@simple-module/ui/components/ui/label';
import { useState } from 'react';

interface Props {
  token: string;
}

function AcceptInvite() {
  const { token: initialToken } = usePage<{ props: Props }>().props as unknown as Props;
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
    fetch('/api/users/auth/accept-invite', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, password }),
    })
      .then(async (res) => {
        if (res.status === 204 || res.status === 200) {
          router.visit('/dashboard');
        } else {
          const data = await res.json().catch(() => ({}));
          const detail = typeof data?.detail === 'string' ? data.detail : '';
          if (detail === 'INVITE_BAD_TOKEN') {
            setError('Invite link has expired or is invalid. Please request a new invitation.');
          } else {
            setError(detail || 'Failed to accept invite. Please try again.');
          }
        }
      })
      .catch(() => setError('An error occurred. Please try again.'))
      .finally(() => setLoading(false));
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-muted p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl">Accept invitation</CardTitle>
          <CardDescription>Set a password to activate your account</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
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
              {loading ? 'Activating…' : 'Activate account'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

export default AcceptInvite;
