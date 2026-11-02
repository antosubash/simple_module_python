import { keys, type TranslationKey } from '@simple-module-py/i18n';
import { type ApiResult, NETWORK_FAILURE } from '@simple-module-py/ui/lib/api';

// The API currently uses English messages as detail codes.
const detailKeys = new Map<string, TranslationKey>([
  ['You cannot manage a more privileged account.', keys.users.admin_errors.more_privileged],
  ['You cannot assign roles you do not hold.', keys.users.admin_errors.roles_not_held],
  ['You cannot disable or demote your own account.', keys.users.admin_errors.own_account],
  ['You cannot remove the last active administrator.', keys.users.admin_errors.last_admin],
  ['You cannot delete your own account.', keys.users.admin_errors.delete_self],
  ['A user with this email already exists.', keys.users.admin_errors.email_exists],
  ['User not found', keys.users.admin_errors.not_found],
  ['External (SSO) users have no password to reset', keys.users.admin_errors.external_password],
]);

/** Translate known admin refusals; unknown details keep the action's fallback. */
export function adminFailureMessage(
  res: Pick<ApiResult<unknown>, 'status' | 'detail'>,
  fallback: string,
  network: string,
  t: (key: TranslationKey) => string,
): string {
  if (res.status === NETWORK_FAILURE) return network;
  const key = res.detail ? detailKeys.get(res.detail) : undefined;
  return key ? t(key) : fallback;
}

/**
 * The text for a failed call: `network` when the request never reached the
 * server, else the server's string `detail` when `useDetail` is set and it sent
 * one, else `fallback`.
 */
export function failureMessage(
  res: ApiResult<unknown>,
  fallback: string,
  network: string,
  useDetail = false,
): string {
  if (res.status === NETWORK_FAILURE) return network;
  return (useDetail ? res.detail : null) ?? fallback;
}
