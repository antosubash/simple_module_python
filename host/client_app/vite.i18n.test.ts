// @vitest-environment node
import { EventEmitter } from 'node:events';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createLogger, createServer, type Plugin, resolveConfig } from 'vite';
import { afterEach, describe, expect, it, vi } from 'vitest';
import scaffoldConfig from '../../framework/cli/simple_module_cli/templates/host/client_app/vite.config.ts';
import hostConfig from './vite.config.ts';

const dirs: string[] = [];
afterEach(() => {
  vi.useRealTimers();
  for (const dir of dirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

type WatcherServer = {
  watcher: Pick<EventEmitter, 'on' | 'off'>;
  config: { server: { watch?: object | null } };
};

function watcherChecks() {
  let failure: string | undefined;
  const logger = createLogger();
  const logError = logger.error;
  logger.error = (message, options) => {
    // Vite can log startup errors before createServer returns its watcher.
    if (message.includes('file watcher error:')) failure = message;
    else logError(message, options);
  };
  return {
    logger,
    async waitFor(server: WatcherServer, check: () => void) {
      const onError = (error: NodeJS.ErrnoException) => {
        failure = `${error.code ?? 'error'}: ${error.message}`;
      };
      server.watcher.on('error', onError);
      try {
        await vi.waitFor(
          () => {
            if (server.config.server.watch === null) failure ??= 'watching is disabled';
            if ('closed' in server.watcher && server.watcher.closed)
              failure ??= 'watcher is closed';
            if (!failure) check();
          },
          { timeout: 5000 },
        );
      } catch (error) {
        if (!failure) throw error;
      } finally {
        server.watcher.off('error', onError);
      }
      if (failure) throw new Error(`Generated i18n file watcher unavailable: ${failure}`);
    },
  };
}

describe('i18n watcher checks', () => {
  function server(watch: null | object = {}) {
    return {
      watcher: Object.assign(new EventEmitter(), { closed: false }),
      config: { server: { watch } },
    };
  }

  it('allows delivery later than the default one-second wait', async () => {
    vi.useFakeTimers();
    let delivered = false;
    setTimeout(() => {
      delivered = true;
    }, 1500);
    const result = watcherChecks()
      .waitFor(server(), () => expect(delivered).toBe(true))
      .then(
        () => undefined,
        (error: Error) => error,
      );
    expect(await result).toBeUndefined();
  });

  it.each(['ENOSPC', 'EMFILE'])(
    'reports a startup %s from Vite before checking files',
    async (code) => {
      const checks = watcherChecks();
      checks.logger.error(`file watcher error: ${code}: watch limit exhausted`);
      await expect(checks.waitFor(server(), () => {})).rejects.toThrow(
        new RegExp(`i18n.*watcher.*${code}`),
      );
    },
  );

  it('reports a chokidar error while waiting for a change', async () => {
    const checks = watcherChecks();
    const vite = server();
    const result = checks.waitFor(vite, () => {
      vite.watcher.emit(
        'error',
        Object.assign(new Error('watch limit exhausted'), { code: 'ENOSPC' }),
      );
      expect(false).toBe(true);
    });
    await expect(result).rejects.toThrow(/i18n.*watcher.*ENOSPC.*watch limit exhausted/);
    expect(vite.watcher.listenerCount('error')).toBe(0);
  });

  it('fails when file watching is disabled', async () => {
    await expect(watcherChecks().waitFor(server(null), () => {})).rejects.toThrow(
      /i18n.*watcher.*disabled/,
    );
  });

  it('fails when the watcher has closed', async () => {
    const vite = server();
    vite.watcher.closed = true;
    await expect(watcherChecks().waitFor(vite, () => {})).rejects.toThrow(/i18n.*watcher.*closed/);
  });
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
            optimizeDeps: {
              force,
              rolldownOptions: { transform: { define: { __EXISTING_DEFINE__: 'true' } } },
            },
          },
          command,
        );
        return {
          resolved,
          plugin: resolved.plugins.find((p) => p.name === plugin?.name),
          optimizerDefines:
            resolved.environments.client.optimizeDeps.rolldownOptions?.transform?.define,
        };
      }
      return { files, hashFile, load };
    }

    it('keeps the optimizer hash input identical for unchanged generated files', async () => {
      const { hashFile, load } = await setup();
      const first = await load();
      expect(first.optimizerDefines?.__SM_I18N_HASH__).toMatch(/^"[a-f0-9]{64}"$/);
      expect(first.optimizerDefines?.__EXISTING_DEFINE__).toBe('true');
      expect(first.resolved.optimizeDeps.force).toBe(false);
      expect((await load()).optimizerDefines).toEqual(first.optimizerDefines);
      expect((await load('serve', true)).resolved.optimizeDeps.force).toBe(true);
      expect(fs.existsSync(hashFile)).toBe(false);
      expect(first.plugin?.buildStart).toBeUndefined();
    });

    it.each([0, 1])(
      'changes the optimizer hash input when generated file %s changes, including on retry',
      async (index) => {
        const { files, hashFile, load } = await setup();
        const first = await load();
        fs.writeFileSync(files[index], 'export const keys = { newKey: true };');
        const changed = await load();
        expect(changed.optimizerDefines?.__SM_I18N_HASH__).not.toBe(
          first.optimizerDefines?.__SM_I18N_HASH__,
        );
        expect(changed.optimizerDefines?.__SM_I18N_HASH__).toMatch(/^"[a-f0-9]{64}"$/);
        expect(changed.resolved.optimizeDeps.force).toBe(false);
        expect((await load()).optimizerDefines).toEqual(changed.optimizerDefines);
        expect(fs.existsSync(hashFile)).toBe(false);
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
        { watcher, restart, config: { logger: { error: vi.fn() } } },
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

    it('does not alter optimizer options or write a hash for a production build', async () => {
      const { hashFile, load } = await setup();
      const { resolved, plugin, optimizerDefines } = await load('build');
      expect(optimizerDefines).toEqual({ __EXISTING_DEFINE__: 'true' });
      expect(resolved.optimizeDeps.force).toBe(false);
      expect(plugin).toBeUndefined();
      expect(fs.existsSync(hashFile)).toBe(false);
    });

    it('receives generated file changes from an installed node_modules package', async () => {
      const { files, load } = await setup();
      const { resolved } = await load();
      const checks = watcherChecks();
      const server = await createServer({
        ...resolved.inlineConfig,
        customLogger: checks.logger,
        server: { middlewareMode: true, ws: false },
        optimizeDeps: { noDiscovery: true, include: [] },
      });
      const restart = vi.spyOn(server, 'restart').mockResolvedValue();
      try {
        await checks.waitFor(server, () => {
          for (const file of files) {
            expect(
              server.watcher.getWatched()[path.dirname(file)],
              `Generated i18n file watcher did not register ${file}`,
            ).toContain(path.basename(file));
          }
        });
        fs.writeFileSync(files[0], 'export const keys = { changed: true };');
        await checks.waitFor(server, () => expect(restart).toHaveBeenCalledExactlyOnceWith(true));
      } finally {
        await server.close();
      }
    }, 15_000);
  });
}
