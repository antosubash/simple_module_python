import { Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { type Role, RolePicker } from './RolePicker';

interface Props {
  email: string;
  fullName: string;
  onEmailChange: (value: string) => void;
  onFullNameChange: (value: string) => void;
  roles: Role[];
  selectedRoles: string[];
  onToggleRole: (roleName: string) => void;
  userId: string;
  hasPermissionsModule: boolean;
  error?: string | null;
}

/**
 * Who this person is and what they can do — name, email and roles together.
 *
 * Roles used to be a card of their own, which read as a separate thing to
 * save even though the page has one Save button covering both. They are an
 * attribute of the account like the name is, so they live beside it.
 */
export function DetailsCard({
  email,
  fullName,
  onEmailChange,
  onFullNameChange,
  roles,
  selectedRoles,
  onToggleRole,
  userId,
  hasPermissionsModule,
  error,
}: Props) {
  const { t } = useT();
  return (
    <Card className="border-border">
      <CardContent className="pt-5">
        <SectionTitle>{t(keys.users.details_card.title)}</SectionTitle>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="edit-full-name" className="text-sm font-medium text-muted-foreground">
              {t(keys.users.common.full_name)}
            </Label>
            <Input
              id="edit-full-name"
              type="text"
              value={fullName}
              onChange={(e) => onFullNameChange(e.target.value)}
              placeholder={t(keys.users.details_card.name_placeholder)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="edit-email" className="text-sm font-medium text-muted-foreground">
              {t(keys.users.common.email)}
            </Label>
            <Input
              id="edit-email"
              type="email"
              value={email}
              onChange={(e) => onEmailChange(e.target.value)}
              autoComplete="off"
            />
          </div>
        </div>

        <div className="mt-4 space-y-2">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="text-sm font-medium text-muted-foreground">
              {t(keys.users.common.roles)}
            </span>
            {hasPermissionsModule && (
              <Link
                href={`/admin/permissions/users/${userId}/edit`}
                className="text-sm font-medium text-primary-700 hover:text-primary-800"
              >
                {t(keys.users.roles_card.manage_permissions)}
              </Link>
            )}
          </div>
          <RolePicker roles={roles} selected={selectedRoles} onToggle={onToggleRole} label="" />
        </div>

        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  );
}
