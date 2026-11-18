// @vitest-environment node
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createServer } from 'vite';
import { afterEach, describe, expect, it } from 'vitest';
import scaffoldConfig, {
  findNodeModulesRoot,
} from '../../framework/cli/simple_module_cli/templates/host/client_app/vite.config.ts';
import hostConfig, { findNodeModulesRoot as findHostNodeModulesRoot } from './vite.config.ts';

const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

function tempDir(): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'smpy-vite-assets-'));
  dirs.push(dir);
  return dir;
}

describe('package-manager install root', () => {
  function install(root: string, manager: string) {
    const pkg = path.join(root, 'node_modules/vite');
    fs.mkdirSync(pkg, { recursive: true });
    fs.writeFileSync(path.join(pkg, 'package.json'), '{}');
    fs.writeFileSync(path.join(root, manager), '');
  }

  for (const [name, findRoot] of [
    ['host', findHostNodeModulesRoot],
    ['scaffold', findNodeModulesRoot],
  ] as const) {
    describe(name, () => {
      it.each(['pnpm-lock.yaml', 'yarn.lock', 'bun.lock', 'package-lock.json'])(
        'finds a hoisted install with %s past a cache-only directory',
        (lockfile) => {
          const workspace = tempDir();
          const client = path.join(workspace, 'host/client_app');
          fs.mkdirSync(path.join(client, 'node_modules/.vite'), { recursive: true });
          install(workspace, lockfile);
          expect(findRoot(client)).toBe(workspace);
        },
      );

      it.each(['pnpm-lock.yaml', 'yarn.lock', 'bun.lock'])(
        'prefers the nearest %s install over a competing npm ancestor',
        (lockfile) => {
          const workspace = tempDir();
          install(workspace, 'package-lock.json');
          fs.writeFileSync(path.join(workspace, 'node_modules/.package-lock.json'), '{}');
          const client = path.join(workspace, 'client_app');
          install(client, lockfile);
          expect(findRoot(client)).toBe(client);
        },
      );

      it('keeps the starting directory when no install is found', () => {
        const client = tempDir();
        fs.mkdirSync(path.join(client, 'node_modules/.vite'), { recursive: true });
        expect(findRoot(client)).toBe(client);
      });
    });
  }
});

for (const [name, config] of [
  ['host', hostConfig],
  ['scaffold', scaffoldConfig],
] as const) {
  it(`${name} pre-bundles generated i18n and refreshes its hash after cache removal`, async () => {
    const options =
      typeof config === 'function'
        ? await config({ command: 'serve', mode: 'development' })
        : await config;
    expect(options.optimizeDeps?.exclude ?? []).not.toContain('@simple-module-py/i18n');

    const root = tempDir();
    const repo = path.resolve(import.meta.dirname, '../..');
    const pkg = path.join(root, 'node_modules/@simple-module-py/i18n');
    fs.mkdirSync(pkg, { recursive: true });
    fs.copyFileSync(path.join(repo, 'packages/i18n/package.json'), path.join(pkg, 'package.json'));
    fs.cpSync(path.join(repo, 'packages/i18n/src'), path.join(pkg, 'src'), { recursive: true });
    for (const dep of ['react', 'i18next', 'react-i18next']) {
      fs.symlinkSync(path.join(repo, 'node_modules', dep), path.join(root, 'node_modules', dep));
    }
    fs.writeFileSync(path.join(root, 'main.ts'), "export { keys } from '@simple-module-py/i18n';");
    const cacheDir = path.join(root, 'node_modules/.vite');
    const runtimeConfig = {
      root,
      configFile: false as const,
      envDir: false as const,
      cacheDir,
      server: { middlewareMode: true, ws: false as const, watch: null },
      optimizeDeps: {
        ...options.optimizeDeps,
        entries: ['main.ts'],
        include: options.optimizeDeps?.include?.filter((dep) =>
          ['react', 'i18next', 'react-i18next', '@simple-module-py/i18n'].includes(dep),
        ),
      },
    };
    const hashes: string[] = [];
    for (const key of ['before', 'after']) {
      fs.writeFileSync(
        path.join(pkg, 'src/keys.generated.ts'),
        `export const keys = { ${key}: '${key}' };`,
      );
      // The Python generator removes this directory on a rewrite (#1003).
      fs.rmSync(cacheDir, { recursive: true, force: true });
      const server = await createServer(runtimeConfig);
      try {
        const entry = await server.transformRequest('/main.ts');
        const url = entry?.code.match(/"([^"]*\/.vite\/deps\/@simple-module-py_i18n[^"]*)"/)?.[1];
        if (!url) throw new Error('i18n was not pre-bundled');
        const optimized = await server.transformRequest(url);
        expect(optimized?.code).toContain(`${key}:`);
        hashes.push(url);
      } finally {
        await server.close();
      }
    }
    expect(hashes[0]).not.toBe(hashes[1]);
  });
}
