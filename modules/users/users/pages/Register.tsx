import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { AuthCardShell } from '@simple-module-py/ui/layouts/AuthCardShell';
import { useState } from 'react';

function Register() {
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setLoading(true);
    fetch('/api/users/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, full_name: fullName }),
    })
      .then(async (res) => {
        if (res.status === 201) {
          setSuccess(true);
        } else {
          const data = await res.json().catch(() => ({}));
          const detail = data?.detail;
          if (detail === 'REGISTER_USER_ALREADY_EXISTS') {
            setError('An account with this email already exists.');
          } else if (typeof detail === 'object' && detail?.code === 'REGISTER_INVALID_PASSWORD') {
            setError(`Password not accepted: ${detail.reason ?? 'too weak'}`);
          } else if (typeof detail === 'string') {
            setError(detail);
          } else {
            setError('Registration failed. Please try again.');
          }
        }
      })
      .catch(() => setError('An error occurred. Please try again.'))
      .finally(() => setLoading(false));
  };

  if (success) {
    return (
      <AuthCardShell>
        <h1 className="text-2xl font-semibold tracking-tight">Check your email</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          We've sent a verification link to <strong>{email}</strong>. Please verify your account
          before signing in.
        </p>
        <a
          href="/users/login"
          className="mt-6 inline-flex items-center justify-center rounded border border-border bg-card px-3 py-2 text-xs font-medium hover:border-primary-400"
        >
          Back to sign in
        </a>
      </AuthCardShell>
    );
  }

  return (
    <AuthCardShell>
      <h1 className="text-2xl font-semibold tracking-tight">Create account</h1>
      <p className="mb-6 mt-1 text-sm text-muted-foreground">
        Fill in your details to get started.
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
          <Label htmlFor="full_name" className="text-xs font-medium">
            Full name
          </Label>
          <Input
            id="full_name"
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="Your name"
            autoComplete="name"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="password" className="text-xs font-medium">
            Password
          </Label>
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="new-password"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="confirm" className="text-xs font-medium">
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

        {error && <p className="text-xs text-destructive">{error}</p>}

        <Button type="submit" className="w-full" disabled={loading}>
          {loading ? 'Creating account…' : 'Create account'}
        </Button>
      </form>

      <p className="mt-4 text-xs text-muted-foreground">
        Already have an account?{' '}
        <a href="/users/login" className="text-primary-700 hover:underline">
          Sign in
        </a>
      </p>
    </AuthCardShell>
  );
}

export default Register;
