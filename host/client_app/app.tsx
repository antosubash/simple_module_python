import { createInertiaApp, router } from '@inertiajs/react';
import { ErrorBoundary } from '@simple-module-py/ui/components/ErrorBoundary';
import { formatTitle, setTitleAppName } from '@simple-module-py/ui/lib/app-title';
import { startSpaLinkInterception } from '@simple-module-py/ui/lib/spa-links';
import { useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { bootI18nFromInitialPage, subscribeI18nToNavigation } from './i18n';
import { resolvePage } from './pages';

// The configured app name is held in the app-title module (Inertia's title
// callback runs outside React and can't read live page props). It's seeded
// below from the initial page's `branding` shared prop, kept fresh by
// BrandingHead, and server-rendered into the root template's static <title> so
// the pre-hydration tab is already branded.
createInertiaApp({
  title: (title) => formatTitle(title),
  resolve: async (name) => {
    const page = await resolvePage(name);
    return page;
  },
  setup({ el, App, props }) {
    const branding = (props.initialPage.props as { branding?: { appName?: string | null } })
      .branding;
    setTitleAppName(branding?.appName);
    bootI18nFromInitialPage(props.initialPage.props);

    function Root() {
      const boundaryRef = useRef<ErrorBoundary>(null);

      useEffect(() => {
        const stopReset = router.on('navigate', () => boundaryRef.current?.reset());
        const stopI18n = subscribeI18nToNavigation();
        // Authored content renders author-entered URLs as plain <a href>, which
        // the browser follows with a full document load — a blank page until
        // this client-rendered app boots again. Route them through Inertia.
        const stopLinks = startSpaLinkInterception();
        return () => {
          stopReset();
          stopI18n();
          stopLinks();
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
