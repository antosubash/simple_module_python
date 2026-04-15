import fs from 'node:fs';
import path from 'node:path';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react-swc';
import { defineConfig } from 'vite';
import tsconfigPaths from 'vite-tsconfig-paths';

const projectRoot = path.resolve(__dirname, '../..');

// Load the module pages manifest written by the Python host at boot.
// Each entry points at an absolute pages/ directory — typically inside a
// pip-installed module wheel. Vite needs these in server.fs.allow so the
// dev server can read files outside the workspace root.
const manifestPath = path.resolve(__dirname, 'modules.manifest.json');
const moduleFsAllow: string[] = [];
const moduleTsconfigs: string[] = [];
if (fs.existsSync(manifestPath)) {
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8')) as Record<string, string>;
  for (const pagesDir of Object.values(manifest)) {
    // Pages live at <moduleRoot>/<pkg>/pages/*.tsx — climb two levels to the
    // module root where its tsconfig.json and package.json live.
    const moduleRoot = path.dirname(path.dirname(pagesDir));
    moduleFsAllow.push(path.dirname(pagesDir));
    const moduleTsconfig = path.join(moduleRoot, 'tsconfig.json');
    if (fs.existsSync(moduleTsconfig)) {
      moduleTsconfigs.push(moduleTsconfig);
    }
  }
}

export default defineConfig({
  // `tsconfigPaths` makes Vite honor each package's tsconfig `paths` at
  // import-resolution time. Each package's `@/*` maps to its own local root,
  // so there's no global `@` alias here — the plugin picks the right tsconfig
  // per importing file.
  plugins: [
    tsconfigPaths({
      projects: [
        path.resolve(__dirname, 'tsconfig.json'),
        path.resolve(projectRoot, 'packages/ui/tsconfig.json'),
        ...moduleTsconfigs,
      ],
    }),
    react(),
    tailwindcss(),
  ],
  root: __dirname,
  build: {
    outDir: '../static/dist',
    manifest: true,
    rollupOptions: {
      input: path.resolve(__dirname, 'main.tsx'),
    },
  },
  server: {
    port: 5050,
    strictPort: true,
    origin: 'http://localhost:5050',
    fs: {
      allow: [projectRoot, ...moduleFsAllow],
    },
  },
});
