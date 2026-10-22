import { usePage } from '@inertiajs/react';
import type { SharedProps } from '../types';

export type PageProps<T extends object> = T & SharedProps & { errors: Record<string, string> };

/**
 * The current page's props, typed as the page's own props `T` plus the shared
 * ones. For components and layouts that cannot receive props as arguments;
 * a page component should declare typed args instead.
 */
export function usePageProps<T extends object = object>(): PageProps<T> {
  // cast-ok: Inertia knows the shared props but not this page's own; `T` is the caller's assertion.
  return usePage().props as unknown as PageProps<T>;
}
