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
import { Share2 } from 'lucide-react';
import type { Share } from '../types';

interface Props {
  shares: Share[];
  canRevoke: boolean;
  highlightId?: string | null;
  onRevoke: (share: Share) => void;
}

export function ShareTable({ shares, canRevoke, highlightId, onRevoke }: Props) {
  const { t } = useT();
  const never = t(keys.sharing.list.never);

  if (shares.length === 0) {
    return (
      <EmptyState
        icon={Share2}
        title={t(keys.sharing.list.empty_title)}
        description={t(keys.sharing.list.empty_description)}
      />
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t(keys.sharing.list.resource)}</TableHead>
            <TableHead>{t(keys.sharing.list.subject)}</TableHead>
            <TableHead>{t(keys.sharing.list.role)}</TableHead>
            <TableHead>{t(keys.sharing.list.granted_by)}</TableHead>
            <TableHead>{t(keys.sharing.list.expires)}</TableHead>
            {canRevoke && (
              <TableHead className="text-right">{t(keys.sharing.list.actions)}</TableHead>
            )}
          </TableRow>
        </TableHeader>
        <TableBody>
          {shares.map((share) => (
            <TableRow key={share.id} data-state={highlightId === share.id ? 'selected' : undefined}>
              <TableCell>
                <div className="font-medium">{share.resource_type}</div>
                <code className="text-xs text-muted-foreground">{share.resource_id}</code>
              </TableCell>
              <TableCell>{share.subject_label ?? share.subject_id}</TableCell>
              <TableCell>
                <Badge variant="secondary">{share.role}</Badge>
              </TableCell>
              <TableCell>{share.granted_by_label ?? share.granted_by}</TableCell>
              <TableCell>
                {formatDayMonthYear(share.expires_at, never)}
                {share.expired && (
                  <Badge variant="outline" className="ml-2">
                    {t(keys.sharing.list.expired)}
                  </Badge>
                )}
              </TableCell>
              {canRevoke && (
                <TableCell className="text-right">
                  <Button variant="ghost" size="sm" onClick={() => onRevoke(share)}>
                    {t(keys.sharing.list.revoke)}
                  </Button>
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
