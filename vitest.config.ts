import react from '@vitejs/plugin-react-swc';
import { defineConfig } from 'vitest/config';
import tsconfigPaths from 'vite-tsconfig-paths';

export default defineConfig({
  plugins: [react(), tsconfigPaths()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    globals: true,
    include: [
      'packages/**/*.test.ts',
      'packages/**/*.test.tsx',
      'host/client_app/**/*.test.ts',
      'host/client_app/**/*.test.tsx',
    ],
  },
});
