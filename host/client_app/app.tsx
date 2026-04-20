import { createInertiaApp, router } from '@inertiajs/react';
import { ErrorBoundary } from '@simple-module/ui/components/ErrorBoundary';
import { useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { bootI18nFromInitialPage, subscribeI18nToNavigation } from './i18n';
import { resolvePage } from './pages';

createInertiaApp({
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
