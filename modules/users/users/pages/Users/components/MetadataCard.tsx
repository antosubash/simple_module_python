import { keys, useT } from '@simple-module-py/i18n';
import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';

interface Props {
  isExternal: boolean;
  createdAt: string | null;
  lastLoginAt: string | null;
  disabledAt: string | null;
  isVerified: boolean;
  savingVerify: boolean;
  onMarkVerified: () => void;
}

/** Read-only account facts, plus the one-shot "mark verified" action. */
export function MetadataCard({
  isExternal,
  createdAt,
  lastLoginAt,
  disabledAt,
  isVerified,
  savingVerify,
  onMarkVerified,
}: Props) {
  const { t } = useT();

  const fmt = (dt: string | null): string =>
    dt ? new Date(dt).toLocaleString() : t(keys.users.common.empty_value);

  return (
    <Card className="border-border">
      <CardContent className="pt-5">
        <SectionTitle>{t(keys.users.metadata_card.title)}</SectionTitle>
        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
          <dt className="text-muted-foreground">{t(keys.users.metadata_card.sign_in)}</dt>
          <dd>
            {isExternal ? (
              <Badge variant="outline" className="border-violet-200 bg-violet-50 text-violet-700">
                {t(keys.users.common.external_badge)}
              </Badge>
            ) : (
              <Badge variant="outline" className="border-border bg-secondary text-muted-foreground">
                {t(keys.users.metadata_card.local_badge)}
              </Badge>
            )}
          </dd>
          <dt className="text-muted-foreground">{t(keys.users.metadata_card.created)}</dt>
          <dd>{fmt(createdAt)}</dd>
          <dt className="text-muted-foreground">{t(keys.users.metadata_card.last_login)}</dt>
          <dd>{lastLoginAt ? fmt(lastLoginAt) : t(keys.users.metadata_card.never)}</dd>
          <dt className="text-muted-foreground">{t(keys.users.metadata_card.disabled_at)}</dt>
          <dd>{fmt(disabledAt)}</dd>
          <dt className="text-muted-foreground">{t(keys.users.metadata_card.verified)}</dt>
          <dd className="flex items-center gap-2">
            {isVerified ? (
              <Badge
                variant="outline"
                className="border-primary-200 bg-primary-50 text-primary-700"
              >
                {t(keys.users.metadata_card.yes)}
              </Badge>
            ) : (
              <>
                <Badge variant="outline" className="border-amber-200 bg-amber-50 text-amber-700">
                  {t(keys.users.metadata_card.no)}
                </Badge>
                {/* Immediate, like the status actions — not part of the
                    page's dirty state. */}
                <Button
                  size="sm"
                  variant="outline"
                  onClick={onMarkVerified}
                  disabled={savingVerify}
                >
                  {savingVerify
                    ? t(keys.users.common.saving)
                    : t(keys.users.metadata_card.mark_verified)}
                </Button>
              </>
            )}
          </dd>
        </dl>
      </CardContent>
    </Card>
  );
}
