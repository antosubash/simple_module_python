// @vitest-environment node
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { simpleModule } from '@simple-module-py/vite-plugin';
import { resolveConfig } from 'vite';
import { afterEach, expect, it } from 'vitest';

const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

it('configures a consuming app from generated manifests and hashes app-owned keys', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'smpy-plugin-'));
  dirs.push(root);
  const pkg = path.join(root, 'wheel/widget');
  fs.mkdirSync(path.join(pkg, 'pages'), { recursive: true });
  fs.writeFileSync(
    path.join(root, 'modules.manifest.json'),
    JSON.stringify({ Widget: `${pkg}/pages/` }),
  );
  fs.writeFileSync(
    path.join(root, 'modules.assets.json'),
    JSON.stringify({
      Widget: {
        package_name: 'widget',
        package: `${pkg}/../widget/`,
        npm_name: '@example/widget',
        ui: `${pkg}/ui`,
      },
    }),
  );
  fs.mkdirSync(path.join(root, 'i18n'));
  for (const name of ['keys.generated.ts', 'generated-resources.ts']) {
    fs.writeFileSync(path.join(root, 'i18n', name), 'export default {};');
  }
  const config = await resolveConfig(
    { root, configFile: false, envDir: false, plugins: simpleModule({ root }) },
    'serve',
  );
  expect(config.resolve.alias).toContainEqual({ find: '@example/widget', replacement: pkg });
  expect(config.server.fs.allow).toContain(pkg);
  expect(config.optimizeDeps.entries).toContain(`${pkg}/pages/**/*.tsx`);
  expect(config.resolve.dedupe).toContain('@inertiajs/react');
  expect(config.optimizeDeps.rolldownOptions?.resolve?.modules).toEqual([
    'node_modules',
    path.join(root, 'node_modules'),
  ]);
  expect(config.optimizeDeps.rolldownOptions?.transform?.define?.__SM_I18N_HASH__).toMatch(
    /^"[a-f0-9]{64}"$/,
  );
});
