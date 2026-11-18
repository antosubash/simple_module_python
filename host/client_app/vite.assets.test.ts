// @vitest-environment node
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createServer, optimizeDeps, resolveConfig } from 'vite';
import { afterEach, describe, expect, it } from 'vitest';
import scaffoldConfig, {
  findNodeModulesRoot,
} from '../../framework/cli/simple_module_cli/templates/host/client_app/vite.config.ts';
import hostConfig from './vite.config.ts';

const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

function tempDir(): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'smpy-vite-assets-'));
  dirs.push(dir);
  return dir;
}

describe('npm install root', () => {
  it.each(['host/client_app', 'client_app'])('skips Vite-only caches in %s', (layout) => {
    const workspace = tempDir();
    const client = path.join(workspace, layout);
    fs.mkdirSync(path.join(client, 'node_modules/.vite'), { recursive: true });
    fs.mkdirSync(path.join(workspace, 'node_modules'));
    fs.writeFileSync(path.join(workspace, 'node_modules/.package-lock.json'), '{}');
    expect(findNodeModulesRoot(client)).toBe(workspace);
  });

  it('uses a real flat install in client_app', () => {
    const client = tempDir();
    fs.mkdirSync(path.join(client, 'node_modules'));
    fs.writeFileSync(path.join(client, 'node_modules/.package-lock.json'), '{}');
    expect(findNodeModulesRoot(client)).toBe(client);
  });

  it('keeps the starting directory when no install is found', () => {
    const client = tempDir();
    fs.mkdirSync(path.join(client, 'node_modules/.vite'), { recursive: true });
    expect(findNodeModulesRoot(client)).toBe(client);
  });
});

for (const [name, config] of [
  ['host', hostConfig],
  ['scaffold', scaffoldConfig],
] as const) {
  it(`${name} serves generated i18n as source and optimizes its dependencies`, async () => {
    const options =
      typeof config === 'function'
        ? await config({ command: 'serve', mode: 'development' })
        : await config;
    expect(options.optimizeDeps?.exclude).toContain('@simple-module-py/i18n');
    expect(options.optimizeDeps?.include).not.toContain('@simple-module-py/i18n');
    expect(options.optimizeDeps?.include).toEqual(
      expect.arrayContaining(['i18next', 'react-i18next']),
    );

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
    const generated = path.join(pkg, 'src/keys.generated.ts');
    fs.writeFileSync(generated, "export const keys = { before: 'before' };");
    const runtimeConfig = {
      root,
      configFile: false as const,
      envDir: false as const,
      cacheDir: path.join(root, 'node_modules/.vite'),
      optimizeDeps: {
        ...options.optimizeDeps,
        entries: ['main.ts'],
        include: options.optimizeDeps?.include?.filter((dep) =>
          ['react', 'i18next', 'react-i18next', '@simple-module-py/i18n'].includes(dep),
        ),
      },
      server: { middlewareMode: true, ws: false as const, watch: null },
    };
    const metadata = await optimizeDeps(await resolveConfig(runtimeConfig, 'serve'));
    expect(metadata.optimized).not.toHaveProperty('@simple-module-py/i18n');
    expect(Object.keys(metadata.optimized)).toEqual(
      expect.arrayContaining(['i18next', 'react-i18next']),
    );
    // Reuse the same optimizer cache across a generated-key rewrite and restart (#1003).
    for (const key of ['before', 'after']) {
      fs.writeFileSync(generated, `export const keys = { ${key}: '${key}' };`);
      const server = await createServer(runtimeConfig);
      try {
        const entry = await server.transformRequest('/main.ts');
        expect(entry?.code).toContain('/node_modules/@simple-module-py/i18n/src/index.ts');
        const source = await server.transformRequest(
          '/node_modules/@simple-module-py/i18n/src/index.ts',
        );
        expect(source?.code).toContain('/.vite/deps/i18next.js');
        expect(source?.code).toContain('/.vite/deps/react-i18next.js');
        const keys = await server.transformRequest(
          '/node_modules/@simple-module-py/i18n/src/keys.generated.ts',
        );
        expect(keys?.code).toContain(`${key}:`);
      } finally {
        await server.close();
      }
    }
  });
}
