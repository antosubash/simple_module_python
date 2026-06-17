import { createInertiaApp, router } from '@inertiajs/react';
import { BrandingHead } from '@simple-module-py/ui/components/BrandingHead';
import { ErrorBoundary } from '@simple-module-py/ui/components/ErrorBoundary';
import { useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { bootI18nFromInitialPage, subscribeI18nToNavigation } from './i18n';
import { resolvePage } from './pages';

// Document-title suffix. Defaults to "SimpleModule" and is updated from the
// branding shared prop on first load and every navigation, so the title
// callback (which only receives the page title) can still reflect the
// configured app name.
let brandAppName = 'SimpleModule';

function appNameFromProps(props: unknown): string | undefined {
  const branding = (props as { branding?: { appName?: string } } | undefined)?.branding;
  return branding?.appName;
}

createInertiaApp({
  title: (title) => (title ? `${title} — ${brandAppName}` : brandAppName),
  resolve: async (name) => {
    const page = await resolvePage(name);
    return page;
  },
  setup({ el, App, props }) {
    bootI18nFromInitialPage(props.initialPage.props);
    brandAppName = appNameFromProps(props.initialPage.props) ?? brandAppName;

    function Root() {
      const boundaryRef = useRef<ErrorBoundary>(null);

      useEffect(() => {
        const stopReset = router.on('navigate', (event) => {
          boundaryRef.current?.reset();
          brandAppName = appNameFromProps(event.detail.page.props) ?? brandAppName;
        });
        const stopI18n = subscribeI18nToNavigation();
        return () => {
          stopReset();
          stopI18n();
        };
      }, []);

      return (
        <ErrorBoundary ref={boundaryRef}>
          <BrandingHead />
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
