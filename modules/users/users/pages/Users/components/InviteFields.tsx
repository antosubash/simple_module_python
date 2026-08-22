import { keys, useT } from '@simple-module-py/i18n';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { Textarea } from '@simple-module-py/ui/components/ui/textarea';
import { Info } from 'lucide-react';

interface Props {
  emails: string;
  onEmailsChange: (value: string) => void;
  /** Valid addresses parsed out of the box so far. */
  count: number;
  invalidEmails: string[];
  mailerDelivers: boolean;
}

export function InviteFields({
  emails,
  onEmailsChange,
  count,
  invalidEmails,
  mailerDelivers,
}: Props) {
  const { t } = useT();
  return (
    <div className="space-y-2">
      <Label htmlFor="emails" className="text-sm font-medium text-muted-foreground">
        {t(keys.users.invite_fields.label)} <span className="text-destructive">*</span>
      </Label>
      <Textarea
        id="emails"
        value={emails}
        onChange={(e) => onEmailsChange(e.target.value)}
        rows={4}
        required
        autoComplete="off"
        // Pasting a column out of a spreadsheet is the actual use case, so
        // newlines have to work as separators alongside commas.
        // i18n-exempt: example email addresses, not prose.
        placeholder={'teammate@example.com\nanother@example.com'}
        className="font-mono text-sm"
      />
      <p className="text-xs text-muted-foreground">
        {t(keys.users.invite_fields.hint)}{' '}
        {count > 0 && t(keys.users.invite_fields.recognised, { count })}
      </p>

      {invalidEmails.length > 0 && (
        <p role="alert" className="text-xs text-destructive">
          {t(keys.users.invite_fields.invalid_email, {
            count: invalidEmails.length,
            email: invalidEmails[0],
          })}
        </p>
      )}

      {!mailerDelivers && (
        <p className="flex items-start gap-1.5 rounded-md bg-amber-50 p-2 text-xs text-amber-900">
          <Info className="mt-0.5 size-3.5 shrink-0" />
          {/* Being told this before submitting beats discovering it after,
              when the invite exists and the recipient has heard nothing. */}
          {t(keys.users.invite_fields.no_mailer)}
        </p>
      )}
    </div>
  );
}
