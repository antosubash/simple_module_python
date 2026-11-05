import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, expect, it } from 'vitest';
import { loadModuleAssets as loadScaffoldAssets } from '../../framework/cli/simple_module_cli/templates/host/client_app/module-assets';
import { loadModuleAssets } from './module-assets';

const roots: string[] = [];
afterEach(() => {
  for (const root of roots.splice(0)) fs.rmSync(root, { recursive: true, force: true });
});

it.each([
  ['host', loadModuleAssets],
  ['scaffold', loadScaffoldAssets],
] as const)('%s resolves UI-only wheel sources and legacy components', (_name, load) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'smp-ui-assets-'));
  roots.push(root);
  const pkg = path.join(root, 'wheel', 'widgets');
  const ui = path.join(pkg, 'ui');
  const components = path.join(pkg, 'components');
  fs.writeFileSync(
    path.join(root, 'modules.assets.json'),
    JSON.stringify({ Widgets: { package_name: 'widgets', package: pkg, ui, components } }),
  );

  const assets = load(root);
  expect(assets.fsAllow).toContain(pkg);
  expect(assets.pagesPrefixes).toContain(ui + path.sep);
  expect(assets.pagesPrefixes).toContain(components + path.sep);
  expect(assets.optimizeEntries).toContain(path.join(ui, '**/*.{ts,tsx}'));
  expect(assets.optimizeEntries).toContain(path.join(components, '**/*.{ts,tsx}'));
});
