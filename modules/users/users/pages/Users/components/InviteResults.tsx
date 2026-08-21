import { keys, useT } from '@simple-module-py/i18n';
import { CopyableId } from '@simple-module-py/ui/components/CopyableId';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { AlertCircle, CheckCircle2, LinkIcon } from 'lucide-react';

export interface InviteResult {
  email: string;
  status: 'sent' | 'link' | 'failed';
  detail?: string;
  link?: string | null;
}

interface Props {
  results: InviteResult[];
  onDismiss: () => void;
}

/**
 * Per-address outcome of a bulk invite, including copyable links.
 *
 * The link panel exists because the console mailer writes invite URLs to
 * stdout and nowhere else: an admin on a dev or self-hosted deployment could
 * create an invite and have no way to deliver it. Links appear only when the
 * server says delivery did not happen, so a working SMTP setup never puts a
 * live token on screen.
 */
export function InviteResults({ results, onDismiss }: Props) {
  const { t } = useT();
  if (results.length === 0) return null;

  const sent = results.filter((r) => r.status === 'sent').length;
  const links = results.filter((r) => r.status === 'link');
  const failed = results.filter((r) => r.status === 'failed');

  async function copyAll() {
    const text = links.map((r) => `${r.email}\t${r.link}`).join('\n');
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Clipboard is unavailable over plain http; the rows are still
      // selectable, so there is nothing useful to say here.
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">
          {sent > 0 && t(keys.users.invite_results.summary_sent, { count: sent })}
          {sent > 0 && (links.length > 0 || failed.length > 0) && ' · '}
          {links.length > 0 && t(keys.users.invite_results.summary_links, { count: links.length })}
          {links.length > 0 && failed.length > 0 && ' · '}
          {failed.length > 0 &&
            t(keys.users.invite_results.summary_failed, { count: failed.length })}
        </h3>
        <Button type="button" variant="ghost" size="sm" onClick={onDismiss}>
          {t(keys.users.invite_results.dismiss)}
        </Button>
      </div>

      {links.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <LinkIcon className="size-3.5" />
              {t(keys.users.invite_results.links_hint)}
            </p>
            {links.length > 1 && (
              <Button type="button" variant="outline" size="sm" onClick={copyAll}>
                {t(keys.users.invite_results.copy_all)}
              </Button>
            )}
          </div>
          <ul className="space-y-1.5">
            {links.map((result) => (
              <li key={result.email} className="flex items-center gap-2 text-xs">
                <span className="w-52 shrink-0 truncate font-medium">{result.email}</span>
                <CopyableId
                  value={result.link ?? ''}
                  label={result.link ?? ''}
                  title={t(keys.users.invite_results.copy_link_title)}
                  className="min-w-0 flex-1"
                />
              </li>
            ))}
          </ul>
        </div>
      )}

      {failed.length > 0 && (
        <ul className="space-y-1">
          {failed.map((result) => (
            <li key={result.email} className="flex items-start gap-1.5 text-xs text-destructive">
              <AlertCircle className="mt-0.5 size-3.5 shrink-0" />
              <span className="font-medium">{result.email}</span>
              <span className="text-muted-foreground">{result.detail}</span>
            </li>
          ))}
        </ul>
      )}

      {sent > 0 && links.length === 0 && failed.length === 0 && (
        <p className="flex items-center gap-1.5 text-xs text-primary-700">
          <CheckCircle2 className="size-3.5" />
          {t(keys.users.invite_results.all_delivered)}
        </p>
      )}
    </div>
  );
}
