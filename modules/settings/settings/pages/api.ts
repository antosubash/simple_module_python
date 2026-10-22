/**
 * Typed client for this module's `/api` routes (#504). The `paths` types are
 * generated from the routes — regenerate with `make gen-api-types` (or
 * `smpy openapi gen-types --module settings`), never edit them by hand.
 */
import { createApi } from '@simple-module-py/ui/lib/api';
import type { paths } from './api.generated';

export const api = createApi<paths>();
