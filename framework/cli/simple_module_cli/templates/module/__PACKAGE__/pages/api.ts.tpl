/**
 * Typed client for this module's `/api` routes. The `paths` types are
 * generated from the routes — regenerate with
 * `smpy openapi gen-types --module {{PACKAGE_NAME}}` after changing an endpoint
 * or DTO, never edit `api.generated.ts` by hand.
 */
import { createApi } from '@simple-module-py/ui/lib/api';
import type { paths } from './api.generated';

export const api = createApi<paths>();
