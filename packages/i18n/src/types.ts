/**
 * Activate i18next TypeScript module augmentation.
 *
 * This file is imported as a side effect from `index.ts`, so every consumer
 * of `@simple-module/i18n` automatically gets typed `t()` — `t('foo.bar')`
 * narrows to the key union emitted by the host into `generated-resources.ts`.
 *
 * Runtime effect: none.
 */

import 'i18next';
import type resources from './generated-resources';

declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'translation';
    resources: typeof resources;
  }
}
