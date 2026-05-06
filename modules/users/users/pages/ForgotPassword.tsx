import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { AuthCardShell } from '@simple-module-py/ui/layouts/AuthCardShell';
import { useState } from 'react';

function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    fetch('/api/users/auth/forgot-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    }).finally(() => {
      setLoading(false);
      setSubmitted(true);
    });
  };

  if (submitted) {
    return (
      <AuthCardShell>
        <h1 className="text-2xl font-semibold tracking-tight">Check your email</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          If an account with that email exists, we've sent a password reset link.
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
      <h1 className="text-2xl font-semibold tracking-tight">Forgot password</h1>
      <p className="mb-6 mt-1 text-sm text-muted-foreground">
        Enter your email to receive a reset link.
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
        <Button type="submit" className="w-full" disabled={loading}>
          {loading ? 'Sending…' : 'Send reset link'}
        </Button>
      </form>
      <p className="mt-4 text-xs text-muted-foreground">
        <a href="/users/login" className="text-primary-700 hover:underline">
          Back to sign in
        </a>
      </p>
    </AuthCardShell>
  );
}

export default ForgotPassword;
