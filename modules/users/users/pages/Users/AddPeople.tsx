import { Head, Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { SegmentedControl } from '@simple-module-py/ui/components/SegmentedControl';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { CreateUserFields } from './components/CreateUserFields';
import { InviteFields } from './components/InviteFields';
import { InviteResults } from './components/InviteResults';
import { MailerBanner } from './components/MailerBanner';
import { type Role, RolePicker } from './components/RolePicker';
import { useAddPeople } from './components/useAddPeople';

interface Props {
  roles: Role[];
  /** False when the configured mailer cannot deliver (console mailer). */
  mailer_delivers: boolean;
  /** Which mailer, so the banner can name the setting to go and change. */
  mailer_name: string;
  invite_expiry_days: number;
}

const USERS_INDEX = '/admin/users/';

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
function AddPeople({
  roles,
  mailer_delivers: mailerDelivers,
  mailer_name: mailerName,
  invite_expiry_days: expiryDays,
}: Props) {
  const { t } = useT();
  const s = useAddPeople();

  return (
    <>
      <Head title={t(keys.users.add_people.title)} />
      <PageShell
        title={t(keys.users.add_people.title)}
        description={t(keys.users.add_people.description)}
        back={USERS_INDEX}
      >
        <SegmentedControl
          value={s.mode}
          onChange={s.changeMode}
          aria-label={t(keys.users.add_people.tablist_label)}
          options={[
            { value: 'invite', label: t(keys.users.add_people.mode_invite) },
            { value: 'create', label: t(keys.users.add_people.mode_create) },
          ]}
          className="mb-4"
        />

        {!mailerDelivers && <MailerBanner mailerName={mailerName} />}

        {/* "Last batch" belongs to the invite flow; creating one account with a
          password you set has no batch to report. */}
        <div
          className={
            s.mode === 'invite' ? 'grid gap-4 lg:grid-cols-[1.25fr_1fr]' : 'grid gap-4 lg:max-w-2xl'
          }
        >
          <Card className="border-border">
            <CardContent className="pt-6">
              <form onSubmit={s.handleSubmit} className="space-y-5">
                {s.mode === 'invite' ? (
                  <InviteFields
                    emails={s.emails}
                    onEmailsChange={s.setEmails}
                    roles={roles}
                    selectedRoles={s.selectedRoles}
                    onToggleRole={s.toggleRole}
                    message={s.message}
                    onMessageChange={s.setMessage}
                  />
                ) : (
                  <>
                    <CreateUserFields
                      email={s.email}
                      fullName={s.fullName}
                      password={s.password}
                      onEmailChange={s.setEmail}
                      onFullNameChange={s.setFullName}
                      onPasswordChange={s.setPassword}
                    />
                    <RolePicker roles={roles} selected={s.selectedRoles} onToggle={s.toggleRole} />
                  </>
                )}

                {s.error && <p className="text-sm text-destructive">{s.error}</p>}

                <div className="flex justify-end gap-2 pt-2">
                  <Button asChild variant="outline" className="max-lg:min-h-11">
                    <Link href={USERS_INDEX}>{t(keys.users.common.cancel)}</Link>
                  </Button>
                  <Button
                    type="submit"
                    disabled={s.loading || !s.canSubmit}
                    className="max-lg:min-h-11"
                  >
                    {s.submitLabel}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>

          {s.mode === 'invite' && (
            <InviteResults
              results={s.results}
              expiryDays={expiryDays}
              onRetry={s.retry}
              retrying={s.retrying}
            />
          )}
        </div>
      </PageShell>
    </>
  );
}

AddPeople.layout = [AdminLayout];
export default AddPeople;
