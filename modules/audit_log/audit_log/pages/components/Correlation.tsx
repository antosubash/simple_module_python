import { keys, useT } from '@simple-module-py/i18n';
import { InlineBanner } from '@simple-module-py/ui/components/InlineBanner';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { GitMerge, X } from 'lucide-react';

/**
 * One request that touches four entities writes four rows. Without a way to
 * pivot on the correlation id they read as four unrelated events, and the id
 * itself was already on the wire — stored, selected and serialised — but never
 * rendered. These two pieces spend it: a per-row pivot, and a banner that says
 * the list is currently showing one action rather than a slice of history.
 */

export function CorrelationLink({
  correlationId,
  onSelect,
}: {
  correlationId: string;
  onSelect: (id: string) => void;
}) {
  const { t } = useT();
  return (
    <button
      type="button"
      onClick={() => onSelect(correlationId)}
      title={t(keys.audit_log.correlation.view_related_title)}
      className="mt-0.5 inline-flex items-center gap-1 text-[11px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
    >
      <GitMerge className="size-3" aria-hidden="true" />
      {t(keys.audit_log.correlation.view_related)}
    </button>
  );
}

export function CorrelationBanner({ count, onClear }: { count: number; onClear: () => void }) {
  const { t } = useT();
  return (
    <InlineBanner
      icon={GitMerge}
      tone="info"
      title={t(keys.audit_log.correlation.banner_title, { count })}
      description={t(keys.audit_log.correlation.banner_description)}
      action={
        <Button variant="outline" size="sm" onClick={onClear} className="gap-1.5">
          <X className="size-3.5" aria-hidden="true" />
          {t(keys.audit_log.correlation.banner_clear)}
        </Button>
      }
    />
  );
}
