import { keys, useT } from '@simple-module-py/i18n';
import { cn } from '@simple-module-py/ui/lib/utils';
import { useState } from 'react';
import { isPlausibleEmail, parseInviteEmails } from '../invite-emails';

interface Props {
  value: string[];
  onChange: (next: string[]) => void;
  id?: string;
  className?: string;
}

/**
 * Addresses as chips, added by Enter, comma or paste.
 *
 * A textarea makes the reader count lines to know how many invites they are
 * about to send, and hides a typo until the server rejects it. A chip is a
 * committed address: the count is the number of chips, and a malformed one
 * turns red the moment it lands rather than after submit.
 *
 * Invalid chips are kept, not refused. Pasting a column out of a spreadsheet
 * is the actual use case, and silently dropping the one bad row would leave
 * someone uninvited with nothing on screen saying so.
 */
export function EmailChipInput({ value, onChange, id, className }: Props) {
  const { t } = useT();
  const [draft, setDraft] = useState('');

  const invalidCount = value.filter((email) => !isPlausibleEmail(email)).length;

  /** Append every address in *raw* that is not already a chip. */
  const commit = (raw: string): boolean => {
    const parsed = parseInviteEmails(raw).map((email) => email.toLowerCase());
    const next = parsed.filter((email, index) => {
      return !value.includes(email) && parsed.indexOf(email) === index;
    });
    if (next.length === 0) return false;
    onChange([...value, ...next]);
    return true;
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' || event.key === ',' || event.key === ' ') {
      // Enter must not submit the surrounding form while the draft still
      // holds an address nobody has committed yet.
      event.preventDefault();
      if (draft.trim()) {
        commit(draft);
        setDraft('');
      }
      return;
    }
    // Backspace on an empty field walks back through the chips, which is what
    // every tag input does and what the muscle memory expects.
    if (event.key === 'Backspace' && draft === '' && value.length > 0) {
      event.preventDefault();
      onChange(value.slice(0, -1));
    }
  };

  const handlePaste = (event: React.ClipboardEvent<HTMLInputElement>) => {
    const text = event.clipboardData.getData('text');
    if (!text) return;
    event.preventDefault();
    commit(text);
    setDraft('');
  };

  return (
    <div className={cn('space-y-1.5', className)}>
      {/* biome-ignore lint/a11y/useKeyWithClickEvents: the click only forwards focus to the input inside, which is itself fully keyboard-operable. */}
      {/* biome-ignore lint/a11y/noStaticElementInteractions: same — this is the field's own padding, not a control. */}
      <div
        className="flex min-h-24 flex-wrap content-start gap-1.5 rounded-lg border border-border bg-card p-3 focus-within:border-primary focus-within:ring-3 focus-within:ring-primary-600/10"
        onClick={(event) => {
          const input = event.currentTarget.querySelector('input');
          input?.focus();
        }}
      >
        {value.map((email) => {
          const valid = isPlausibleEmail(email);
          return (
            <span
              key={email}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium',
                valid
                  ? 'bg-primary-600/10 text-primary-700 dark:text-primary-400'
                  : 'bg-red-500/10 text-red-700 dark:text-red-400',
              )}
            >
              <span data-valid={valid ? 'true' : 'false'}>{email}</span>
              <button
                type="button"
                aria-label={t(keys.users.invite_fields.remove_chip, { email })}
                onClick={() => onChange(value.filter((other) => other !== email))}
                // The chip is 26px tall by design, so the tap area is grown
                // with a pseudo-element instead of the box: `min-h-11` here
                // would stretch every chip on a phone.
                className="relative text-current/60 transition-colors hover:text-current max-lg:after:absolute max-lg:after:top-1/2 max-lg:after:left-1/2 max-lg:after:h-11 max-lg:after:w-11 max-lg:after:-translate-x-1/2 max-lg:after:-translate-y-1/2 max-lg:after:content-['']"
              >
                ✕
              </button>
            </span>
          );
        })}
        <input
          id={id}
          type="text"
          value={draft}
          autoComplete="off"
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          // Clicking Send with an address still in the draft would otherwise
          // silently drop it — blur commits before the click lands.
          onBlur={() => {
            if (draft.trim() && commit(draft)) setDraft('');
          }}
          placeholder={value.length === 0 ? t(keys.users.invite_fields.chip_placeholder) : ''}
          className="min-w-40 flex-1 bg-transparent text-sm outline-none max-lg:min-h-11 placeholder:text-muted-foreground"
        />
      </div>
      {/* "0 addresses" under an empty box states the obvious and reads as an
          error the reader has to rule out. The count starts when there is
          something to count. */}
      {value.length > 0 && (
        <p className="text-xs text-muted-foreground">
          {invalidCount > 0
            ? t(keys.users.invite_fields.counter, {
                count: value.length,
                invalid: invalidCount,
              })
            : t(keys.users.invite_fields.counter_clean, { count: value.length })}
        </p>
      )}
    </div>
  );
}
