// @vitest-environment node
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { resolveConfig } from 'vite';
import { afterEach, expect, it } from 'vitest';
import { simpleModule } from './index';

const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

it('resolves host dependencies from wheel pages, UI and legacy components', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'smpy-resolve-'));
  dirs.push(root);
  const wheel = path.join(root, 'external/widget');
  fs.mkdirSync(path.join(root, 'node_modules/host-dep'), { recursive: true });
  fs.mkdirSync(wheel, { recursive: true });
  fs.writeFileSync(
    path.join(root, 'node_modules/host-dep/package.json'),
    '{"name":"host-dep","exports":"./index.js"}',
  );
  fs.writeFileSync(path.join(root, 'node_modules/host-dep/index.js'), 'export const value = 1;');
  fs.writeFileSync(
    path.join(root, 'modules.manifest.json'),
    JSON.stringify({ Widget: `${wheel}/pages` }),
  );
  fs.writeFileSync(
    path.join(root, 'modules.assets.json'),
    JSON.stringify({
      Widget: {
        package_name: 'widget',
        package: wheel,
        npm_name: '@example/widget',
        ui: `${wheel}/ui`,
        components: `${wheel}/components`,
      },
    }),
  );
  const config = await resolveConfig(
    { root, configFile: false, envDir: false, plugins: simpleModule({ root }) },
    'build',
  );
  const resolver = config.plugins.find(
    (p) => p.name === 'simple-module:resolve-module-bare-imports',
  );
  const hook = resolver?.resolveId;
  if (!hook) throw new Error('missing module resolver');
  const resolve = config.createResolver();
  const invoke = (source: string, importer: string) =>
    Reflect.apply(
      typeof hook === 'function' ? hook : hook.handler,
      { resolve: (source: string, importer: string) => resolve(source, importer) },
      [source, importer],
    );
  for (const area of ['pages', 'ui', 'components']) {
    expect(await invoke('host-dep', `${wheel}/${area}/Widget.tsx?version=1`)).toBe(
      path.join(root, 'node_modules/host-dep/index.js'),
    );
  }
  for (const source of ['./relative', '/absolute', '\0virtual', 'virtual:test']) {
    expect(await invoke(source, `${wheel}/pages/Widget.tsx`)).toBeNull();
  }
  expect(await invoke('host-dep', `${wheel}/pages-other/Widget.tsx`)).toBeNull();
  expect(await invoke('missing-dep', `${wheel}/pages/Widget.tsx`)).toBeNull();
});
