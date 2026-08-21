import { Link, router, usePage } from '@inertiajs/react';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import type React from 'react';
import { useState } from 'react';
import { toast } from 'sonner';
import { CreateUserFields } from './components/CreateUserFields';
import { InviteFields } from './components/InviteFields';
import { type InviteResult, InviteResults } from './components/InviteResults';
import { type Role, RolePicker } from './components/RolePicker';

type Mode = 'invite' | 'create';

interface Props {
  roles: Role[];
  /** False when the configured mailer cannot deliver (console mailer). */
  mailer_delivers: boolean;
}

const USERS_INDEX = '/admin/users/';

function initialMode(): Mode {
  if (typeof window === 'undefined') return 'invite';
  return new URLSearchParams(window.location.search).get('mode') === 'create' ? 'create' : 'invite';
}

/**
 * One screen for both ways of adding people.
 *
 * Create and invite were separate pages behind separate buttons, so an admin
 * had to choose before seeing what either involved. They take nearly the same
 * inputs and differ in exactly one respect — whether the admin sets the
 * password or the person does — which makes it a mode switch, not a fork in
 * the navigation.
 */
function AddPeople() {
  const { roles, mailer_delivers: mailerDelivers } = usePage<{ props: Props }>()
    .props as unknown as Props;

  const [mode, setMode] = useState<Mode>(initialMode);
  const [selectedRoles, setSelectedRoles] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<InviteResult[]>([]);

  // Invite mode
  const [emails, setEmails] = useState('');
  // Create mode
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');

  const toggleRole = (roleName: string) =>
    setSelectedRoles((prev) =>
      prev.includes(roleName) ? prev.filter((r) => r !== roleName) : [...prev, roleName],
    );

  /** Split a pasted block on commas, semicolons, and any whitespace. */
  const parsedEmails = emails
    .split(/[\s,;]+/)
    .map((value) => value.trim())
    .filter(Boolean);

  async function submitInvite() {
    const resp = await fetch('/api/users/admin/invite/bulk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ emails: parsedEmails, role_names: selectedRoles }),
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      setError(typeof body?.detail === 'string' ? body.detail : 'Failed to send invites');
      return;
    }
    const body = await resp.json();
    const next: InviteResult[] = body.results ?? [];
    setResults(next);

    const sent = next.filter((r) => r.status === 'sent').length;
    if (sent > 0) toast.success(`${sent} invite${sent === 1 ? '' : 's'} sent`);

    // Only clear the box when nothing needs following up — otherwise the
    // admin loses the list they still have to act on.
    if (next.every((r) => r.status === 'sent')) {
      setEmails('');
      router.visit(USERS_INDEX);
    }
  }

  async function submitCreate() {
    const resp = await fetch('/api/users/admin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email,
        password,
        full_name: fullName || null,
        role_names: selectedRoles,
      }),
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      setError(typeof body?.detail === 'string' ? body.detail : 'Failed to create user');
      return;
    }
    toast.success('User created');
    router.visit(USERS_INDEX);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setResults([]);
    setLoading(true);
    try {
      await (mode === 'invite' ? submitInvite() : submitCreate());
    } catch {
      setError('An error occurred. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  const canSubmit =
    mode === 'invite' ? parsedEmails.length > 0 : email.trim() !== '' && password !== '';

  return (
    <PageShell
      title="Add people"
      description="Invite them to set their own password, or create the account yourself."
      actions={
        <Button asChild variant="outline">
          <Link href={USERS_INDEX}>Back to Users</Link>
        </Button>
      }
    >
      <Card className="max-w-2xl border-border">
        <CardContent className="space-y-5 pt-6">
          <div
            role="tablist"
            aria-label="How to add people"
            className="inline-flex rounded-lg border border-border bg-secondary/40 p-1"
          >
            {(['invite', 'create'] as Mode[]).map((value) => (
              <button
                key={value}
                type="button"
                role="tab"
                aria-selected={mode === value}
                onClick={() => {
                  setMode(value);
                  setError(null);
                }}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                  mode === value
                    ? 'bg-card text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {value === 'invite' ? 'Send invites' : 'Create account'}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            {mode === 'invite' ? (
              <InviteFields
                emails={emails}
                onEmailsChange={setEmails}
                count={parsedEmails.length}
                mailerDelivers={mailerDelivers}
              />
            ) : (
              <CreateUserFields
                email={email}
                fullName={fullName}
                password={password}
                onEmailChange={setEmail}
                onFullNameChange={setFullName}
                onPasswordChange={setPassword}
              />
            )}

            <RolePicker roles={roles} selected={selectedRoles} onToggle={toggleRole} />

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="flex justify-end gap-2 pt-2">
              <Button asChild variant="outline">
                <Link href={USERS_INDEX}>Cancel</Link>
              </Button>
              <Button type="submit" disabled={loading || !canSubmit}>
                {loading
                  ? 'Working…'
                  : mode === 'invite'
                    ? `Send ${parsedEmails.length || ''} invite${parsedEmails.length === 1 ? '' : 's'}`.trim()
                    : 'Create user'}
              </Button>
            </div>
          </form>

          <InviteResults results={results} onDismiss={() => setResults([])} />
        </CardContent>
      </Card>
    </PageShell>
  );
}

AddPeople.layout = (page: React.ReactNode) => <AdminLayout>{page}</AdminLayout>;
export default AddPeople;
