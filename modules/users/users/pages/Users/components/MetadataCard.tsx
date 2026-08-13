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

function fmt(dt: string | null): string {
  if (!dt) return '—';
  return new Date(dt).toLocaleString();
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
  return (
    <Card className="border-border">
      <CardContent className="pt-5">
        <SectionTitle>Metadata</SectionTitle>
        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
          <dt className="text-muted-foreground">Sign-in</dt>
          <dd>
            {isExternal ? (
              <Badge variant="outline" className="border-violet-200 bg-violet-50 text-violet-700">
                External · SSO
              </Badge>
            ) : (
              <Badge variant="outline" className="border-border bg-secondary text-muted-foreground">
                Local · password
              </Badge>
            )}
          </dd>
          <dt className="text-muted-foreground">Created</dt>
          <dd>{fmt(createdAt)}</dd>
          <dt className="text-muted-foreground">Last login</dt>
          <dd>{lastLoginAt ? fmt(lastLoginAt) : 'Never'}</dd>
          <dt className="text-muted-foreground">Disabled at</dt>
          <dd>{fmt(disabledAt)}</dd>
          <dt className="text-muted-foreground">Verified</dt>
          <dd className="flex items-center gap-2">
            {isVerified ? (
              <Badge
                variant="outline"
                className="border-primary-200 bg-primary-50 text-primary-700"
              >
                yes
              </Badge>
            ) : (
              <>
                <Badge variant="outline" className="border-amber-200 bg-amber-50 text-amber-700">
                  no
                </Badge>
                {/* Immediate, like the status actions — not part of the
                    page's dirty state. */}
                <Button
                  size="sm"
                  variant="outline"
                  onClick={onMarkVerified}
                  disabled={savingVerify}
                >
                  {savingVerify ? 'Saving…' : 'Mark verified'}
                </Button>
              </>
            )}
          </dd>
        </dl>
      </CardContent>
    </Card>
  );
}
