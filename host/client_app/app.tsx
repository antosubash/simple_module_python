import { createInertiaApp, router } from '@inertiajs/react';
import { ErrorBoundary } from '@simple-module/ui/components/ErrorBoundary';
import { getCsrfToken, setCsrfToken } from '@simple-module/ui/lib/csrf';
import { useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { bootI18nFromInitialPage, subscribeI18nToNavigation } from './i18n';
import { resolvePage } from './pages';

function readCsrfToken(pageProps: unknown): string {
  if (pageProps && typeof pageProps === 'object' && 'csrf_token' in pageProps) {
    const token = (pageProps as { csrf_token?: unknown }).csrf_token;
    if (typeof token === 'string') return token;
  }
  return '';
}

// Stamp every non-GET Inertia visit with the server's session-scoped CSRF
// token. Raw fetch() callers use ``fetchWithCsrf`` which reads from the same
// module-level store that ``setCsrfToken`` updates.
router.on('before', (event) => {
  const method = event.detail.visit.method?.toLowerCase();
  const token = getCsrfToken();
  if (method && method !== 'get' && token) {
    event.detail.visit.headers = {
      ...(event.detail.visit.headers ?? {}),
      'X-CSRF-Token': token,
    };
  }
});

router.on('success', (event) => {
  const next = readCsrfToken(event.detail.page.props);
  if (next) setCsrfToken(next);
});

createInertiaApp({
  resolve: async (name) => {
    const page = await resolvePage(name);
    return page;
  },
  setup({ el, App, props }) {
    setCsrfToken(readCsrfToken(props.initialPage.props));
    bootI18nFromInitialPage(props.initialPage.props);

    function Root() {
      const boundaryRef = useRef<ErrorBoundary>(null);

      useEffect(() => {
        const stopReset = router.on('navigate', () => boundaryRef.current?.reset());
        const stopI18n = subscribeI18nToNavigation();
        return () => {
          stopReset();
          stopI18n();
        };
      }, []);

      return (
        <ErrorBoundary ref={boundaryRef}>
          <App {...props} />
        </ErrorBoundary>
      );
    }

    createRoot(el).render(<Root />);
  },
  progress: {
    color: '#4B5563',
    delay: 150,
  },
});
