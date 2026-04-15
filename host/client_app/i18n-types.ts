/**
 * Activate i18next TypeScript module augmentation.
 *
 * Imported once from main.tsx so t('foo.bar') is type-checked against
 * generated-resources.ts. Runtime effect: none.
 */

import 'i18next';
import type resources from './generated-resources';

declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'translation';
    resources: typeof resources;
  }
}
