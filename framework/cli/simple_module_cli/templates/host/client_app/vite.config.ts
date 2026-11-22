import path from 'node:path';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import { simpleModule } from '@simple-module-py/vite-plugin';
import { viteDevServer } from './vite.dev-url.ts';

export { findNodeModulesRoot } from '@simple-module-py/vite-plugin';

const { origin: devUrl, port: devPort } = viteDevServer();

export default defineConfig(({ command }) => ({
  plugins: [...simpleModule({ root: import.meta.dirname }), react(), tailwindcss()],
  root: import.meta.dirname,
  base: command === 'build' ? '/static/dist/' : '/',
  // The supervisor resolves dotenv once; standalone launches and builds use Vite's loader.
  envDir: command === 'serve' && process.env.SM_DEV_SUPERVISED === '1' ? false : undefined,
  build: {
    outDir: '../static/dist',
    manifest: true,
    rollupOptions: {
      input: path.resolve(import.meta.dirname, 'main.tsx'),
    },
  },
  server: {
    port: devPort,
    strictPort: true,
    origin: devUrl,
  },
}));
