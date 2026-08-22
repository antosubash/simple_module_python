import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  resolve: {
    tsconfigPaths: true,
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    globals: true,
    include: [
      'packages/**/*.test.ts',
      'packages/**/*.test.tsx',
      'host/client_app/**/*.test.ts',
      'host/client_app/**/*.test.tsx',
      'modules/**/tests-js/**/*.test.ts',
      'modules/**/tests-js/**/*.test.tsx',
      // The lint gates are code too — a "fix" to one of their heuristics
      // should not be able to quietly stop them detecting anything.
      'scripts/**/*.test.mts',
    ],
  },
});
