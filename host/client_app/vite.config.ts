import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';
import path from 'path';

const projectRoot = path.resolve(__dirname, '../..');

export default defineConfig({
    plugins: [tailwindcss()],
    esbuild: {
        jsx: 'automatic',
    },
    root: __dirname,
    resolve: {
        alias: {
            '@ui': path.resolve(projectRoot, 'packages/ui/src'),
            '@modules': path.resolve(projectRoot, 'modules'),
        },
    },
    build: {
        outDir: '../static/dist',
        manifest: true,
        rollupOptions: {
            input: path.resolve(__dirname, 'main.tsx'),
        },
    },
    server: {
        port: 5173,
        origin: 'http://localhost:5173',
        fs: {
            allow: [projectRoot],
        },
    },
});
