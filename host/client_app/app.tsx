import { createInertiaApp, router } from '@inertiajs/react';
import { ErrorBoundary } from '@simple-module-py/ui/components/ErrorBoundary';
import { useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { bootI18nFromInitialPage, subscribeI18nToNavigation } from './i18n';
import { resolvePage } from './pages';

// NOTE: the browser-tab title is not branded with the configured app name.
// The in-app branding (sidebar name/logo, favicon, primary colour) is applied
// via the `branding` shared prop + BrandingHead; wiring the configured name
// into the document <title> is a deferred follow-up (Inertia's title callback
// can't read live page props, and this app's title updates are page-driven).
createInertiaApp({
  title: (title) => (title ? `${title} — SimpleModule` : 'SimpleModule'),
  resolve: async (name) => {
    const page = await resolvePage(name);
    return page;
  },
  setup({ el, App, props }) {
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
