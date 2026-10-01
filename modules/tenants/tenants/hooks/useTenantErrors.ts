import { keys, useT } from '@simple-module-py/i18n';

/**
 * Maps the API's stable `{detail: code}` error codes to translated copy.
 *
 * Built inside a hook (never at module scope) so it stays bound to the
 * active locale rather than freezing against whatever locale was live on
 * first render.
 */
export function useTenantErrors() {
  const { t } = useT();

  const messages: Record<string, string> = {
    slug_taken: t(keys.tenants.errors.slug_taken),
    self_service_disabled: t(keys.tenants.errors.self_service_disabled),
    tenant_suspended: t(keys.tenants.errors.tenant_suspended),
    not_found: t(keys.tenants.errors.not_found),
    last_owner: t(keys.tenants.errors.last_owner),
    owner_required: t(keys.tenants.errors.owner_required),
    member_not_found: t(keys.tenants.errors.member_not_found),
    already_invited: t(keys.tenants.errors.already_invited),
    already_member: t(keys.tenants.errors.already_member),
    tenant_manager_required: t(keys.tenants.errors.tenant_manager_required),
    tenant_isolation: t(keys.tenants.errors.tenant_isolation),
    invitation_not_found: t(keys.tenants.errors.invitation_not_found),
    invitation_expired: t(keys.tenants.errors.invitation_expired),
    invitation_used: t(keys.tenants.errors.invitation_used),
    invitation_email_mismatch: t(keys.tenants.errors.invitation_email_mismatch),
  };

  /** Reads a fetch Response body's `{detail}` (and `limit` for plan_limit) and
   * returns translated copy, falling back to a generic message. */
  async function describe(response: Response): Promise<string> {
    if (response.status === 422) return t(keys.tenants.errors.validation_failed);
    const data = await response.json().catch(() => ({}) as Record<string, unknown>);
    const code = typeof data.detail === 'string' ? data.detail : '';
    if (code === 'plan_limit') {
      return t(keys.tenants.errors.plan_limit, { limit: data.limit ?? '?' });
    }
    return messages[code] ?? t(keys.tenants.errors.generic);
  }

  return { describe };
}
