import { keys, useT } from '@simple-module-py/i18n';
import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { useRelativeTime } from '@simple-module-py/ui/hooks/use-relative-time';

export interface LinkedSignIn {
  provider: string;
  username: string | null;
  subject: string | null;
  last_sign_in_at: string | null;
}

interface Props {
  links: LinkedSignIn[];
}

/**
 * Which identity provider accounts sign in as this person (#877).
 *
 * Read-only: the provider's username and subject say which IdP identity an
 * account belongs to, which an administrator otherwise cannot tell.
 */
export function LinkedSignInsCard({ links }: Props) {
  const { t } = useT();
  const { ago } = useRelativeTime();
  return (
    <Card className="border-border">
      <CardContent className="pt-5">
        <SectionTitle>{t(keys.users.linked_sign_ins.title)}</SectionTitle>
        <ul className="space-y-3 text-sm">
          {links.map((link) => (
            <li key={`${link.provider}-${link.subject ?? link.username}`} className="space-y-0.5">
              <p className="font-medium">
                {link.provider}
                {link.username && (
                  <span className="font-normal text-muted-foreground"> · {link.username}</span>
                )}
              </p>
              {link.subject && (
                <p className="break-all text-xs text-muted-foreground">
                  {t(keys.users.linked_sign_ins.subject)} <code>{link.subject}</code>
                </p>
              )}
              <p className="text-xs text-muted-foreground">
                {link.last_sign_in_at
                  ? t(keys.users.linked_sign_ins.last_sign_in, { when: ago(link.last_sign_in_at) })
                  : t(keys.users.linked_sign_ins.never)}
              </p>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
