import { keys, useT } from '@simple-module-py/i18n';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { cn } from '@simple-module-py/ui/lib/utils';
import { toast } from 'sonner';

export interface InviteResult {
  email: string;
  status: 'sent' | 'link' | 'failed';
  detail?: string;
  link?: string | null;
}

interface Props {
  results: InviteResult[];
  /** Days an invite token stays usable, from the module's own settings. */
  expiryDays: number;
  /** Re-posts this single address through the bulk endpoint. */
  onRetry: (email: string) => void;
  retrying: string | null;
}

/**
 * "Last batch" — the outcome of the most recent submit, kept beside the form.
 *
 * It used to appear below the form and then vanish: a fully successful batch
 * redirected to the users list, so the one case where an admin wants to
 * confirm what they just did was the one case they never saw. Kept in React
 * state rather than persisted — it describes this sitting, and a stale batch
 * from yesterday reading "2 sent" would be worse than an empty panel.
 *
 * Links appear only when the server says delivery did not happen, so a working
 * SMTP setup never puts a live invite token on screen.
 */
export function InviteResults({ results, expiryDays, onRetry, retrying }: Props) {
  const { t } = useT();
  const sent = results.filter((r) => r.status !== 'failed').length;
  const failed = results.length - sent;

  async function copyLink(link: string) {
    try {
      await navigator.clipboard.writeText(link);
      toast.success(t(keys.users.invite_results.toast_copied));
    } catch {
      toast.error(t(keys.users.invite_results.copy_failed));
    }
  }

  return (
    <Card className="flex flex-col overflow-hidden border-border p-0">
      <div className="flex items-center gap-3 border-b px-4 py-3.5">
        <h2 className="flex-1 text-[15px] font-bold font-[var(--font-display)]">
          {t(keys.users.invite_results.title)}
        </h2>
        {results.length > 0 && (
          <span className="text-xs text-muted-foreground">
            {t(keys.users.invite_results.meta_sent, { count: sent })}
            {' · '}
            {t(keys.users.invite_results.meta_failed, { count: failed })}
          </span>
        )}
      </div>

      {results.length === 0 ? (
        <p className="px-4 py-6 text-sm text-muted-foreground">
          {t(keys.users.invite_results.empty)}
        </p>
      ) : (
        <ul>
          {results.map((result) => (
            <li
              key={result.email}
              className={cn(
                'flex flex-col gap-1 border-b px-4 py-3.5 text-sm',
                result.status === 'failed' && 'bg-red-500/5',
              )}
            >
              <div className="flex items-center gap-2.5">
                <span
                  aria-hidden="true"
                  className={
                    result.status === 'failed'
                      ? 'text-destructive'
                      : 'text-primary-700 dark:text-primary-400'
                  }
                >
                  {result.status === 'failed' ? '✕' : '✓'}
                </span>
                <span className="min-w-0 flex-1 truncate">{result.email}</span>
                {result.status === 'failed' ? (
                  <button
                    type="button"
                    onClick={() => onRetry(result.email)}
                    disabled={retrying === result.email}
                    className="text-xs font-medium text-muted-foreground transition-colors hover:text-foreground disabled:opacity-60 max-lg:min-h-11 max-lg:px-2"
                  >
                    {retrying === result.email
                      ? t(keys.users.invite_results.retrying)
                      : t(keys.users.invite_results.retry)}
                  </button>
                ) : (
                  result.link && (
                    <button
                      type="button"
                      onClick={() => copyLink(result.link ?? '')}
                      className="text-xs font-medium text-primary-700 transition-colors hover:text-primary-800 dark:text-primary-400 max-lg:min-h-11 max-lg:px-2"
                    >
                      {t(keys.users.invite_results.copy_link)}
                    </button>
                  )
                )}
              </div>
              {result.status === 'failed' && result.detail && (
                <span className="pl-6 text-xs text-destructive">{result.detail}</span>
              )}
            </li>
          ))}
        </ul>
      )}

      <p className="px-4 py-4 text-xs leading-relaxed text-muted-foreground">
        {t(keys.users.invite_results.expiry_note, { count: expiryDays })}
      </p>
    </Card>
  );
}
