// @vitest-environment node
import { EventEmitter } from 'node:events';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createServer, type Plugin, resolveConfig, type ViteDevServer } from 'vite';
import { afterEach, describe, expect, it, vi } from 'vitest';
import scaffoldConfig from '../../framework/cli/simple_module_cli/templates/host/client_app/vite.config.ts';
import hostConfig from './vite.config.ts';

const dirs: string[] = [];
afterEach(() => {
  vi.useRealTimers();
  for (const dir of dirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

for (const [name, config] of [
  ['host', hostConfig],
  ['scaffold', scaffoldConfig],
] as const) {
  describe(`${name} generated i18n`, () => {
    async function setup() {
      const root = fs.mkdtempSync(path.join(os.tmpdir(), 'smpy-vite-i18n-'));
      dirs.push(root);
      const pkg = path.join(root, 'node_modules/@simple-module-py/i18n');
      fs.mkdirSync(path.join(pkg, 'src'), { recursive: true });
      fs.writeFileSync(path.join(pkg, 'package.json'), '{"exports":"./src/index.ts"}');
      fs.writeFileSync(path.join(pkg, 'src/index.ts'), 'export const keys = {};');
      const files = ['keys.generated.ts', 'generated-resources.ts'].map((file) =>
        path.join(pkg, 'src', file),
      );
      for (const file of files) fs.writeFileSync(file, 'export const keys = {};');
      const cacheDir = path.join(root, 'custom-cache');
      const hashFile = path.join(cacheDir, 'sm-i18n.hash');
      async function load(command: 'serve' | 'build' = 'serve', force = false) {
        const options =
          typeof config === 'function'
            ? await config({ command, mode: 'development' })
            : await config;
        const plugin = options.plugins
          ?.flat()
          .find((p) => p && 'name' in p && p.name === 'simple-module:i18n-generated') as
          | Plugin
          | undefined;
        expect(plugin, 'the Vite config must install the i18n plugin').toBeDefined();
        const resolved = await resolveConfig(
          {
            root,
            cacheDir,
            configFile: false,
            envDir: false,
            plugins: [plugin],
            optimizeDeps: { force },
          },
          command,
        );
        return { resolved, plugin: resolved.plugins.find((p) => p.name === plugin?.name) };
      }
      function start(plugin: Plugin | undefined) {
        const hook = plugin?.buildStart;
        if (hook) return Reflect.apply(typeof hook === 'function' ? hook : hook.handler, {}, [{}]);
      }
      return { files, hashFile, load, start };
    }

    it('forces optimization for a missing hash, then reuses unchanged generated files', async () => {
      const { hashFile, load, start } = await setup();
      const first = await load();
      expect(first.resolved.optimizeDeps.force).toBe(true);
      expect(fs.existsSync(hashFile)).toBe(false);
      await start(first.plugin);
      expect(fs.readFileSync(hashFile, 'utf8')).toMatch(/^[a-f0-9]{64}$/);
      const second = await load();
      expect(second.resolved.optimizeDeps.force).toBe(false);
      expect((await load('serve', true)).resolved.optimizeDeps.force).toBe(true);
    });

    it.each([0, 1])(
      'forces optimization and rewrites the hash when generated file %s changes',
      async (index) => {
        const { files, hashFile, load, start } = await setup();
        await start((await load()).plugin);
        const previous = fs.readFileSync(hashFile, 'utf8');
        fs.writeFileSync(files[index], 'export const keys = { newKey: true };');
        const changed = await load();
        expect(changed.resolved.optimizeDeps.force).toBe(true);
        expect(changed.resolved.environments.client.optimizeDeps.force).toBe(true);
        expect(fs.readFileSync(hashFile, 'utf8')).toBe(previous);
        await start(changed.plugin);
        expect(fs.readFileSync(hashFile, 'utf8')).not.toBe(previous);
        expect((await load()).resolved.optimizeDeps.force).toBe(false);
      },
    );

    it('watches both generated files and debounces a forced server restart', async () => {
      const { files, load } = await setup();
      const { plugin } = await load();
      const watcher = Object.assign(new EventEmitter(), { add: vi.fn() });
      const restart = vi.fn().mockResolvedValue(undefined);
      const hook = plugin?.configureServer;
      expect(hook).toBeDefined();
      if (!hook) return;
      Reflect.apply(typeof hook === 'function' ? hook : hook.handler, {}, [
        { watcher, restart, config: { logger: { error: vi.fn() } } } as Partial<ViteDevServer>,
      ]);
      expect(watcher.add).toHaveBeenCalledWith(files);
      vi.useFakeTimers();
      watcher.emit('change', path.join(path.dirname(files[0]), 'index.ts'));
      await vi.runAllTimersAsync();
      expect(restart).not.toHaveBeenCalled();
      for (const file of files) watcher.emit('change', file);
      expect(restart).not.toHaveBeenCalled();
      await vi.runAllTimersAsync();
      expect(restart).toHaveBeenCalledExactlyOnceWith(true);
    });

    it('does not force optimization or write a hash for a production build', async () => {
      const { hashFile, load } = await setup();
      const { resolved, plugin } = await load('build');
      expect(resolved.optimizeDeps.force).toBe(false);
      expect(plugin).toBeUndefined();
      expect(fs.existsSync(hashFile)).toBe(false);
    });

    it('receives generated file changes from an installed node_modules package', async () => {
      const { files, load } = await setup();
      const { resolved } = await load();
      const server = await createServer({
        ...resolved.inlineConfig,
        server: { middlewareMode: true, ws: false },
        optimizeDeps: { noDiscovery: true, include: [] },
      });
      const restart = vi.spyOn(server, 'restart').mockResolvedValue();
      try {
        await vi.waitFor(() => {
          expect(Object.values(server.watcher.getWatched()).flat()).toContain('keys.generated.ts');
        });
        fs.writeFileSync(files[0], 'export const keys = { changed: true };');
        await vi.waitFor(() => expect(restart).toHaveBeenCalledExactlyOnceWith(true));
      } finally {
        await server.close();
      }
    });
  });
}
