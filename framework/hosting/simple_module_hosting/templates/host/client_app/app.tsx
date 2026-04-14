import { createInertiaApp } from '@inertiajs/react';
import { createRoot } from 'react-dom/client';
import { resolvePage } from './pages';

createInertiaApp({
  resolve: async (name) => {
    return await resolvePage(name);
  },
  setup({ el, App, props }) {
    createRoot(el).render(<App {...props} />);
  },
  progress: {
    color: '#4B5563',
    delay: 150,
  },
});
