import { Head, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import type React from 'react';
import { PasswordCard } from '../auth_local/components/PasswordCard';
import { PreferencesCard } from '../auth_local/components/PreferencesCard';
import { ProfileDetailsCard } from '../auth_local/components/ProfileDetailsCard';
import type { ProfileUser } from '../auth_local/components/profile-user';
import { SessionsCard } from '../auth_local/components/SessionsCard';

interface Props {
  user: ProfileUser;
}

/**
 * Your own account.
 *
 * The page reads its `user` from a prop the view loads, not from the shared
 * `auth.user`: that context carries id, email, name and roles, and the page
 * used to ask it for `full_name` and `is_verified`, which it has never had —
 * so the name box always loaded blank and the badge always said "unverified".
 */
function Profile() {
  const { user } = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();

  if (!user) return null;

  return (
    <>
      <Head title={t(keys.users.profile.head_title)} />
      <PageShell
        title={t(keys.users.profile.title)}
        description={t(keys.users.profile.description)}
      >
        <div className="grid items-start gap-4 lg:grid-cols-[1.2fr_1fr]">
          <div className="space-y-4">
            <ProfileDetailsCard user={user} />
            {/* An SSO account has no local password to change. */}
            {!user.is_external && <PasswordCard />}
          </div>
          <div className="space-y-4">
            <SessionsCard lastLoginAt={user.last_login_at} />
            <PreferencesCard />
          </div>
        </div>
      </PageShell>
    </>
  );
}

Profile.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Profile;
