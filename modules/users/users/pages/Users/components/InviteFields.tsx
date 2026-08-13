import { Label } from '@simple-module-py/ui/components/ui/label';
import { Textarea } from '@simple-module-py/ui/components/ui/textarea';
import { Info } from 'lucide-react';

interface Props {
  emails: string;
  onEmailsChange: (value: string) => void;
  /** Addresses parsed out of the box so far. */
  count: number;
  mailerDelivers: boolean;
}

export function InviteFields({ emails, onEmailsChange, count, mailerDelivers }: Props) {
  return (
    <div className="space-y-2">
      <Label htmlFor="emails" className="text-sm font-medium text-muted-foreground">
        Email addresses <span className="text-destructive">*</span>
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
        placeholder={'teammate@example.com\nanother@example.com'}
        className="font-mono text-sm"
      />
      <p className="text-xs text-muted-foreground">
        One per line, or separated by commas. {count > 0 && `${count} recognised.`}
      </p>

      {!mailerDelivers && (
        <p className="flex items-start gap-1.5 rounded-md bg-amber-50 p-2 text-xs text-amber-900">
          <Info className="mt-0.5 size-3.5 shrink-0" />
          {/* Being told this before submitting beats discovering it after,
              when the invite exists and the recipient has heard nothing. */}
          This deployment logs invite mail instead of sending it. You will get a copyable link for
          each address to pass on yourself.
        </p>
      )}
    </div>
  );
}
