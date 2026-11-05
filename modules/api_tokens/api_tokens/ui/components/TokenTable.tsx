import { keys, useT } from '@simple-module-py/i18n';
import { EmptyState } from '@simple-module-py/ui/components/EmptyState';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module-py/ui/components/ui/table';
import { formatDayMonthYear } from '@simple-module-py/ui/lib/date-format';
import { KeyRound } from 'lucide-react';
import { type ApiToken, type TokenStatus, tokenStatus } from '../types';

interface Props {
  tokens: ApiToken[];
  /** Admin view: show kind and owner columns. */
  showOwner?: boolean;
  highlightId?: string | null;
  onRevoke: (token: ApiToken) => void;
}

const STATUS_VARIANT: Record<TokenStatus, 'secondary' | 'outline' | 'destructive'> = {
  active: 'secondary',
  revoked: 'destructive',
  expired: 'outline',
};

export function TokenTable({ tokens, showOwner = false, highlightId, onRevoke }: Props) {
  const { t } = useT();
  const statusLabel: Record<TokenStatus, string> = {
    active: t(keys.api_tokens.status.active),
    revoked: t(keys.api_tokens.status.revoked),
    expired: t(keys.api_tokens.status.expired),
  };
  const never = t(keys.api_tokens.list.never);

  if (tokens.length === 0) {
    return (
      <EmptyState
        icon={KeyRound}
        title={t(keys.api_tokens.list.empty_title)}
        description={t(keys.api_tokens.list.empty_description)}
      />
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t(keys.api_tokens.list.name)}</TableHead>
            {showOwner && <TableHead>{t(keys.api_tokens.list.kind)}</TableHead>}
            {showOwner && <TableHead>{t(keys.api_tokens.list.owner)}</TableHead>}
            <TableHead>{t(keys.api_tokens.list.scopes)}</TableHead>
            <TableHead>{t(keys.api_tokens.list.expires)}</TableHead>
            <TableHead>{t(keys.api_tokens.list.last_used)}</TableHead>
            <TableHead>{t(keys.api_tokens.list.status)}</TableHead>
            <TableHead className="text-right">{t(keys.api_tokens.list.actions)}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {tokens.map((token) => {
            const status = tokenStatus(token);
            return (
              <TableRow
                key={token.id}
                data-state={highlightId === token.id ? 'selected' : undefined}
              >
                <TableCell>
                  <div className="font-medium">{token.name}</div>
                  <code className="text-xs text-muted-foreground">{token.prefix}…</code>
                </TableCell>
                {showOwner && (
                  <TableCell>
                    {token.kind === 'service'
                      ? t(keys.api_tokens.kind.service)
                      : t(keys.api_tokens.kind.personal)}
                  </TableCell>
                )}
                {showOwner && (
                  <TableCell className="text-sm">
                    {token.owner_email ?? token.roles.join(', ')}
                  </TableCell>
                )}
                <TableCell>
                  <Badge variant="outline" title={token.scopes.join('\n')}>
                    {t(keys.api_tokens.list.scope_count, { count: token.scopes.length })}
                  </Badge>
                </TableCell>
                <TableCell className="text-sm">
                  {formatDayMonthYear(token.expires_at, never)}
                </TableCell>
                <TableCell className="text-sm">
                  {formatDayMonthYear(token.last_used_at, never)}
                </TableCell>
                <TableCell>
                  <Badge variant={STATUS_VARIANT[status]}>{statusLabel[status]}</Badge>
                </TableCell>
                <TableCell className="text-right">
                  {status === 'active' && (
                    <Button variant="ghost" size="sm" onClick={() => onRevoke(token)}>
                      {t(keys.api_tokens.list.revoke)}
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
