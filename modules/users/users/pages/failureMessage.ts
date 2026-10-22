import { type ApiResult, NETWORK_FAILURE } from '@simple-module-py/ui/lib/api';

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
