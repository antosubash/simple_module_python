/**
 * Activate i18next TypeScript module augmentation.
 *
 * This file is imported as a side effect from `index.ts`, so every consumer
 * of `@simple-module-py/i18n` automatically gets typed `t()` — `t('foo.bar')`
 * narrows to shipped keys plus app-owned and module-local augmentations.
 *
 * Runtime effect: none.
 */

import 'i18next';
import type resources from './generated-resources';
import type { TranslationResources } from './index';

declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'translation';
    resources: { translation: typeof resources.translation & TranslationResources };
  }
}
