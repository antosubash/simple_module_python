import { createInertiaApp, router } from '@inertiajs/react';
import { ErrorBoundary } from '@simple-module/ui/components/ErrorBoundary';
import { useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { resolvePage } from './pages';

createInertiaApp({
  resolve: async (name) => {
    const page = await resolvePage(name);
    return page;
  },
  setup({ el, App, props }) {
    function Root() {
      const boundaryRef = useRef<ErrorBoundary>(null);

      useEffect(() => {
        // Reset the boundary on navigation so the next page can render.
        return router.on('navigate', () => boundaryRef.current?.reset());
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
