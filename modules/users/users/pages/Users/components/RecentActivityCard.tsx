import { Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';

export interface ActivityEntry {
  at: string;
  summary: string;
  href: string;
}

interface Props {
  entries: ActivityEntry[];
  userId: string;
}

/**
 * `14:02:11` for today, `12 Mar 14:02` for anything older.
 *
 * A bare clock reads as "just now" whatever it says, so an entry from last
 * month would look like this afternoon's. The date only appears when it
 * changes the answer.
 */
function stamp(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  const time = parsed.toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
  if (parsed.toDateString() === new Date().toDateString()) return time;
  const date = parsed.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
  return `${date} ${time.slice(0, 5)}`;
}

/**
 * What this person has been doing, from the audit log.
 *
 * Rendered only when the audit_log module is installed — the page passes
 * `null` otherwise, and an absent card is the honest rendering of a
 * deployment that records nothing. Filtered by actor rather than by subject:
 * an admin looking at an account wants to know what its owner did, not what
 * was done to them.
 */
export function RecentActivityCard({ entries, userId }: Props) {
  const { t } = useT();
  return (
    <Card className="border-border">
      <CardContent className="flex h-full flex-col pt-5">
        <SectionTitle>{t(keys.users.recent_activity.title)}</SectionTitle>
        {entries.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t(keys.users.recent_activity.empty)}</p>
        ) : (
          <ul className="space-y-2.5 text-sm">
            {entries.map((entry) => (
              <li key={`${entry.at}-${entry.summary}`} className="flex gap-3">
                <span className="w-[86px] shrink-0 font-mono text-xs text-muted-foreground">
                  {stamp(entry.at)}
                </span>
                <Link href={entry.href} className="flex-1 hover:text-primary-700">
                  {entry.summary}
                </Link>
              </li>
            ))}
          </ul>
        )}
        <Link
          href={`/admin/audit-log/?user_id=${userId}`}
          className="mt-auto pt-4 text-sm font-medium text-primary-700 hover:text-primary-800"
        >
          {t(keys.users.recent_activity.see_all)}
        </Link>
      </CardContent>
    </Card>
  );
}
