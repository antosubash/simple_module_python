import { Link, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
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
import { isPlausibleEmail, parseInviteEmails } from './invite-emails';

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
  const { t } = useT();

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

  const parsedEmails = parseInviteEmails(emails);
  const invalidEmails = parsedEmails.filter((value) => !isPlausibleEmail(value));
  const validEmailCount = parsedEmails.length - invalidEmails.length;

  async function submitInvite() {
    const resp = await fetch('/api/users/admin/invite/bulk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ emails: parsedEmails, role_names: selectedRoles }),
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      setError(
        typeof body?.detail === 'string'
          ? body.detail
          : t(keys.users.add_people.error_invite_failed),
      );
      return;
    }
    const body = await resp.json();
    const next: InviteResult[] = body.results ?? [];
    setResults(next);

    const sent = next.filter((r) => r.status === 'sent').length;
    if (sent > 0) toast.success(t(keys.users.add_people.toast_invites_sent, { count: sent }));

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
      setError(
        typeof body?.detail === 'string'
          ? body.detail
          : t(keys.users.add_people.error_create_failed),
      );
      return;
    }
    toast.success(t(keys.users.add_people.toast_user_created));
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
      setError(t(keys.users.common.error_try_again));
    } finally {
      setLoading(false);
    }
  }

  const canSubmit =
    mode === 'invite'
      ? validEmailCount > 0 && invalidEmails.length === 0
      : email.trim() !== '' && password !== '';

  const submitLabel = loading
    ? t(keys.users.add_people.submitting)
    : mode === 'invite'
      ? t(keys.users.add_people.submit_invite, { count: parsedEmails.length })
      : t(keys.users.add_people.submit_create);

  return (
    <PageShell
      title={t(keys.users.add_people.title)}
      description={t(keys.users.add_people.description)}
      actions={
        <Button asChild variant="outline">
          <Link href={USERS_INDEX}>{t(keys.users.common.back_to_users)}</Link>
        </Button>
      }
    >
      <Card className="max-w-2xl border-border">
        <CardContent className="space-y-5 pt-6">
          <div
            role="tablist"
            aria-label={t(keys.users.add_people.tablist_label)}
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
                {value === 'invite'
                  ? t(keys.users.add_people.mode_invite)
                  : t(keys.users.add_people.mode_create)}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            {mode === 'invite' ? (
              <InviteFields
                emails={emails}
                onEmailsChange={setEmails}
                count={validEmailCount}
                invalidEmails={invalidEmails}
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
                <Link href={USERS_INDEX}>{t(keys.users.common.cancel)}</Link>
              </Button>
              <Button type="submit" disabled={loading || !canSubmit}>
                {submitLabel}
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
