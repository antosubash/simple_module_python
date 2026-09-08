import { Link, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { InlineBanner } from '@simple-module-py/ui/components/InlineBanner';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { SegmentedControl } from '@simple-module-py/ui/components/SegmentedControl';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { TriangleAlert } from 'lucide-react';
import type React from 'react';
import { useState } from 'react';
import { toast } from 'sonner';
import { CreateUserFields } from './components/CreateUserFields';
import { InviteFields } from './components/InviteFields';
import { type InviteResult, InviteResults } from './components/InviteResults';
import { type Role, RolePicker } from './components/RolePicker';
import { isPlausibleEmail } from './invite-emails';

type Mode = 'invite' | 'create';

interface Props {
  roles: Role[];
  /** False when the configured mailer cannot deliver (console mailer). */
  mailer_delivers: boolean;
  /** Which mailer, so the banner can name the setting to go and change. */
  mailer_name: string;
  invite_expiry_days: number;
}

const USERS_INDEX = '/admin/users/';
const SETTINGS_URL = '/admin/settings/';
const BULK_INVITE_URL = '/api/users/admin/invite/bulk';

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
 *
 * A fully successful batch stays on the page. Redirecting to the users list
 * was throwing away the confirmation at exactly the moment it was earned, and
 * with a console mailer it also threw away the only copy of the links.
 */
function AddPeople() {
  const {
    roles,
    mailer_delivers: mailerDelivers,
    mailer_name: mailerName,
    invite_expiry_days: expiryDays,
  } = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();

  const [mode, setMode] = useState<Mode>(initialMode);
  const [selectedRoles, setSelectedRoles] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<InviteResult[]>([]);
  const [retrying, setRetrying] = useState<string | null>(null);

  // Invite mode
  const [emails, setEmails] = useState<string[]>([]);
  const [message, setMessage] = useState('');
  // Create mode
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');

  const toggleRole = (roleName: string) =>
    setSelectedRoles((prev) =>
      prev.includes(roleName) ? prev.filter((r) => r !== roleName) : [...prev, roleName],
    );

  // Invalid chips are excluded rather than blocking: one typo in a pasted
  // column must not hold up the other nineteen addresses.
  const validEmails = emails.filter(isPlausibleEmail);

  async function postInvites(addresses: string[]): Promise<InviteResult[] | null> {
    const resp = await fetch(BULK_INVITE_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        emails: addresses,
        role_names: selectedRoles,
        message: message.trim() || null,
      }),
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      setError(
        typeof body?.detail === 'string'
          ? body.detail
          : t(keys.users.add_people.error_invite_failed),
      );
      return null;
    }
    return (await resp.json()).results ?? [];
  }

  async function submitInvite() {
    const next = await postInvites(validEmails);
    if (next === null) return;
    setResults(next);
    const sent = next.filter((r) => r.status === 'sent').length;
    if (sent > 0) toast.success(t(keys.users.add_people.toast_invites_sent, { count: sent }));
    // Only clear the box when nothing needs following up — otherwise the
    // admin loses the list they still have to act on.
    if (next.every((r) => r.status !== 'failed')) {
      setEmails([]);
      setMessage('');
    }
  }

  /** Re-post one address, replacing just its row in the last batch. */
  async function retry(address: string) {
    setRetrying(address);
    setError(null);
    try {
      const next = await postInvites([address]);
      if (next === null || next.length === 0) return;
      setResults((prev) => prev.map((row) => (row.email === address ? next[0] : row)));
    } catch {
      setError(t(keys.users.common.error_try_again));
    } finally {
      setRetrying(null);
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
    mode === 'invite' ? validEmails.length > 0 : email.trim() !== '' && password !== '';

  const submitLabel = loading
    ? t(keys.users.add_people.submitting)
    : mode === 'invite'
      ? t(keys.users.add_people.submit_invite, { count: validEmails.length })
      : t(keys.users.add_people.submit_create);

  return (
    <PageShell
      title={t(keys.users.add_people.title)}
      description={t(keys.users.add_people.description)}
      back={USERS_INDEX}
    >
      <SegmentedControl
        value={mode}
        onChange={(next) => {
          setMode(next);
          setError(null);
        }}
        aria-label={t(keys.users.add_people.tablist_label)}
        options={[
          { value: 'invite', label: t(keys.users.add_people.mode_invite) },
          { value: 'create', label: t(keys.users.add_people.mode_create) },
        ]}
        className="mb-4"
      />

      {!mailerDelivers && (
        // One sentence, as the deck has it — a title/body pair reads as two
        // separate facts when it is really one: which mailer, and what that
        // means for the links. The "Configure SMTP" link ends the sentence
        // rather than sitting right-aligned away from what it refers to.
        <InlineBanner
          icon={TriangleAlert}
          tone="warning"
          align="start"
          title={
            <span className="font-normal">
              {t(keys.users.add_people.mailer_banner_prefix)} <b>{mailerName}</b>{' '}
              {t(keys.users.add_people.mailer_banner_suffix)}{' '}
              {/* The 44px tap area is grown with a pseudo-element: an inline
                  link inside a sentence cannot take `min-h-11` without
                  stretching the line box around it. */}
              <Link
                href={SETTINGS_URL}
                className="relative font-medium underline max-lg:after:absolute max-lg:after:top-1/2 max-lg:after:left-0 max-lg:after:h-11 max-lg:after:w-full max-lg:after:-translate-y-1/2 max-lg:after:content-['']"
              >
                {t(keys.users.add_people.configure_smtp)}
              </Link>
            </span>
          }
        />
      )}

      {/* "Last batch" belongs to the invite flow; creating one account with a
          password you set has no batch to report. */}
      <div
        className={
          mode === 'invite' ? 'grid gap-4 lg:grid-cols-[1.25fr_1fr]' : 'grid gap-4 lg:max-w-2xl'
        }
      >
        <Card className="border-border">
          <CardContent className="pt-6">
            <form onSubmit={handleSubmit} className="space-y-5">
              {mode === 'invite' ? (
                <InviteFields
                  emails={emails}
                  onEmailsChange={setEmails}
                  roles={roles}
                  selectedRoles={selectedRoles}
                  onToggleRole={toggleRole}
                  message={message}
                  onMessageChange={setMessage}
                />
              ) : (
                <>
                  <CreateUserFields
                    email={email}
                    fullName={fullName}
                    password={password}
                    onEmailChange={setEmail}
                    onFullNameChange={setFullName}
                    onPasswordChange={setPassword}
                  />
                  <RolePicker roles={roles} selected={selectedRoles} onToggle={toggleRole} />
                </>
              )}

              {error && <p className="text-sm text-destructive">{error}</p>}

              <div className="flex justify-end gap-2 pt-2">
                <Button asChild variant="outline" className="max-lg:min-h-11">
                  <Link href={USERS_INDEX}>{t(keys.users.common.cancel)}</Link>
                </Button>
                <Button type="submit" disabled={loading || !canSubmit} className="max-lg:min-h-11">
                  {submitLabel}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        {mode === 'invite' && (
          <InviteResults
            results={results}
            expiryDays={expiryDays}
            onRetry={retry}
            retrying={retrying}
          />
        )}
      </div>
    </PageShell>
  );
}

AddPeople.layout = (page: React.ReactNode) => <AdminLayout>{page}</AdminLayout>;
export default AddPeople;
