import { router, usePage } from '@inertiajs/react';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { AuthCardShell } from '@simple-module-py/ui/layouts/AuthCardShell';
import { CheckCircle2 } from 'lucide-react';
import { useState } from 'react';

interface Props {
  token: string;
}

function AcceptInvite() {
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
    fetch('/api/users/auth/accept-invite', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, password }),
    })
      .then(async (res) => {
        if (res.status === 204 || res.status === 200) {
          router.visit('/dashboard/');
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
    <AuthCardShell>
      <div className="flex items-start gap-3 rounded-xl border border-primary-200 bg-primary-50 p-3 text-sm text-primary-800">
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <div>
          <p className="font-semibold">You've been invited</p>
          <p className="mt-0.5">Pick a password and you'll be signed in.</p>
        </div>
      </div>
      <h1 className="mt-5 mb-1.5 text-[22px] font-bold tracking-tight font-[var(--font-display)] text-foreground">
        Set your password
      </h1>
      <form onSubmit={handleSubmit} className="space-y-3.5">
        <div className="space-y-1.5">
          <Label htmlFor="password" className="text-sm font-medium text-muted-foreground">
            Password
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
          {loading ? 'Activating…' : 'Set password & sign in'}
        </Button>
      </form>
      {token && (
        <p className="mt-4 text-center font-mono text-[11px] text-muted-foreground">
          token={token.slice(0, 16)}…
        </p>
      )}
    </AuthCardShell>
  );
}

export default AcceptInvite;
