import { keys, useT } from '@simple-module-py/i18n';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { Textarea } from '@simple-module-py/ui/components/ui/textarea';
import { useId } from 'react';
import { EmailChipInput } from './EmailChipInput';
import { type Role, RolePicker } from './RolePicker';

interface Props {
  emails: string[];
  onEmailsChange: (next: string[]) => void;
  roles: Role[];
  selectedRoles: string[];
  onToggleRole: (roleName: string) => void;
  message: string;
  onMessageChange: (value: string) => void;
}

/**
 * Everything one batch of invitations needs: who, what access, and why.
 *
 * The roles label spells out that they apply to the whole batch — a role
 * picker sitting under a list of five addresses reads as though it belongs to
 * whichever one you were last looking at.
 */
export function InviteFields({
  emails,
  onEmailsChange,
  roles,
  selectedRoles,
  onToggleRole,
  message,
  onMessageChange,
}: Props) {
  const { t } = useT();
  const emailsId = useId();
  const messageId = useId();

  return (
    <>
      <div className="space-y-2">
        <Label htmlFor={emailsId} className="text-sm font-medium">
          {t(keys.users.invite_fields.label)}
        </Label>
        <EmailChipInput id={emailsId} value={emails} onChange={onEmailsChange} />
      </div>

      <RolePicker
        roles={roles}
        selected={selectedRoles}
        onToggle={onToggleRole}
        label={t(keys.users.invite_fields.roles_label)}
      />

      <div className="space-y-2">
        <Label htmlFor={messageId} className="text-sm font-medium">
          {t(keys.users.invite_fields.message_label)}
        </Label>
        {/* An invitation from an address nobody recognises is indistinguishable
            from phishing; one line of context is what makes it answerable. */}
        <Textarea
          id={messageId}
          value={message}
          onChange={(e) => onMessageChange(e.target.value)}
          rows={2}
          maxLength={1000}
          placeholder={t(keys.users.invite_fields.message_placeholder)}
        />
      </div>
    </>
  );
}
