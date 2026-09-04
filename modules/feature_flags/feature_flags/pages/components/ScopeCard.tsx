import { Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { TenantPicker } from './TenantPicker';

interface Props {
  tenantId: string | null;
  tenants: string[];
  /** Audit log filtered to override rows, or null when none is installed. */
  auditLogUrl: string | null;
  onSelect: (tenantId: string | null) => void;
}

// Word Joiner: a zero-width character that cannot appear in real copy, used to
// find where the translator put the tenant id so it can be rendered in the mono
// face. Interpolating twice and splitting keeps word order the translator's
// choice, which pinning the id to the end of the sentence would not.
const SLOT = '\u2060';

/**
 * The scope row above the table: which tenant is being looked at, what that
 * means for unset flags, and a way into the history of every change.
 */
export function ScopeCard({ tenantId, tenants, auditLogUrl, onSelect }: Props) {
  const { t } = useT();
  const [hintBefore, hintAfter] = tenantId
    ? t(keys.feature_flags.browse.viewing_tenant, { tenant_id: SLOT }).split(SLOT)
    : [t(keys.feature_flags.browse.viewing_system), ''];

  return (
    <Card className="mb-4 flex flex-row flex-wrap items-center gap-x-3 gap-y-2 p-4">
      <span className="text-sm font-medium text-muted-foreground">
        {t(keys.feature_flags.browse.scope_label)}
      </span>
      <TenantPicker tenantId={tenantId} tenants={tenants} onSelect={onSelect} />
      <p className="text-sm text-muted-foreground">
        {hintBefore}
        {tenantId && <code className="font-mono text-xs">{tenantId}</code>}
        {hintAfter}
      </p>
      {auditLogUrl && (
        <Link
          href={auditLogUrl}
          className="text-xs font-medium text-primary-700 hover:underline sm:ml-auto"
        >
          {t(keys.feature_flags.browse.view_history)}
        </Link>
      )}
    </Card>
  );
}
