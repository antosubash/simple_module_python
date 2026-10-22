/**
 * Typed client for this module's `/api` routes (#504). The `paths` types are
 * generated from the routes — regenerate with `make gen-api-types` (or
 * `smpy openapi gen-types --module api_tokens`), never edit them by hand.
 *
 * Mutations sit behind `RequiresCsrf`. The client sends the session's
 * `csrfToken` shared prop; these pages also receive their own `csrf_token`
 * prop and pin it per call with `csrfHeaders`.
 */
import { createApi } from '@simple-module-py/ui/lib/api';
import type { paths } from './api.generated';

export const api = createApi<paths>();

export function csrfHeaders(token: string): Record<string, string> {
  return { 'X-CSRF-Token': token };
}
