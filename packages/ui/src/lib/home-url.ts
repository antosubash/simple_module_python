import { usePage } from '@inertiajs/react';
import type { SharedProps } from '../types';

/**
 * The app's home URL from the `homeUrl` shared prop (the users module's
 * `login_redirect_url`), or `/` when no module supplies one.
 */
export function useHomeUrl(): string {
  const { homeUrl } = usePage<{ props: SharedProps }>().props as unknown as SharedProps;
  // Same-origin paths only: the value is admin-editable and now feeds hrefs.
  return homeUrl && /^\/(?![/\\])/.test(homeUrl) ? homeUrl : '/';
}
