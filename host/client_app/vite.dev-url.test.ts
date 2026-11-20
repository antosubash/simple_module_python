// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest';
import { viteDevServer as scaffoldDevServer } from '../../framework/cli/simple_module_cli/templates/host/client_app/vite.dev-url.ts';
import { viteDevServer } from './vite.dev-url.ts';

// Both shipped configurations must preserve direct launches as well as supervision.
afterEach(() => vi.unstubAllEnvs());
for (const [name, resolve] of [
  ['host', viteDevServer],
  ['scaffold', scaffoldDevServer],
] as const) {
  describe(name, () => {
    it.each([
      [undefined, undefined, 5050],
      [undefined, '5201', 5050],
      ['http://localhost:5207', '5201', 5207],
    ])('resolves URL %s ignoring removed SM_VITE_PORT %s', (url, port, expected) => {
      vi.stubEnv('SM_VITE_DEV_URL', url);
      vi.stubEnv('SM_VITE_PORT', port);
      expect(resolve()).toEqual({ origin: `http://localhost:${expected}`, port: expected });
    });
  });
}

// Resolve actual Vite configurations without building or binding a socket.
it.each(['host', 'scaffold'])('%s loads build dotenv outside supervised dev', async (name) => {
  const { resolveConfig } = await import('vite');
  const { mkdtemp, writeFile, rm } = await import('node:fs/promises');
  const { tmpdir } = await import('node:os');
  const { join } = await import('node:path');
  const dir = await mkdtemp(join(tmpdir(), 'smpy-vite-'));
  const config =
    name === 'host'
      ? (await import('./vite.config.ts')).default
      : (
          await import(
            '../../framework/cli/simple_module_cli/templates/host/client_app/vite.config.ts'
          )
        ).default;
  try {
    await writeFile(join(dir, '.env.production'), 'VITE_PIPELINE_PROBE=production\n');
    await writeFile(join(dir, '.env.development'), 'VITE_PIPELINE_PROBE=development\n');
    for (const [command, supervised, expected] of [
      ['build', '1', 'production'],
      ['serve', undefined, 'development'],
      ['serve', '1', undefined],
    ] as const) {
      vi.stubEnv('SM_DEV_SUPERVISED', supervised);
      const options =
        typeof config === 'function'
          ? await config({ command, mode: command === 'build' ? 'production' : 'development' })
          : config;
      const resolved = await resolveConfig(
        {
          ...options,
          root: dir,
          mode: command === 'build' ? 'production' : 'development',
          configFile: false,
          plugins: [],
        },
        command,
      );
      expect(resolved.env.VITE_PIPELINE_PROBE).toBe(expected);
    }
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
