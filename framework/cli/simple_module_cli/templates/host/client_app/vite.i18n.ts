import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { normalizePath, type Plugin } from 'vite';

export function i18nGenerated(): Plugin {
  let files: string[] = [];
  let hashFile: string;
  let hash: string;
  let restartTimer: ReturnType<typeof setTimeout> | undefined;
  return {
    name: 'simple-module:i18n-generated',
    apply: 'serve',
    async configResolved(config) {
      const entry = await config.createResolver()(
        '@simple-module-py/i18n',
        path.join(config.root, 'package.json'),
      );
      if (!entry) throw new Error('Cannot resolve @simple-module-py/i18n');
      files = ['keys.generated.ts', 'generated-resources.ts'].map((name) =>
        normalizePath(path.join(path.dirname(entry), name)),
      );
      const digest = createHash('sha256');
      for (const file of files) digest.update(fs.readFileSync(file)).update('\0');
      hash = digest.digest('hex');
      hashFile = path.join(config.cacheDir, 'sm-i18n.hash');
      config.optimizeDeps.force ||=
        !fs.existsSync(hashFile) || fs.readFileSync(hashFile, 'utf8') !== hash;
      // Explicitly added installed files must bypass Vite's node_modules ignore.
      if (config.server.watch !== null) {
        const ignored = config.server.watch?.ignored;
        config.server.watch = {
          ...config.server.watch,
          ignored: [
            ...(Array.isArray(ignored) ? ignored : ignored ? [ignored] : []),
            ...files.map((file) => `!${file}`),
          ],
        };
      }
    },
    buildStart() {
      fs.mkdirSync(path.dirname(hashFile), { recursive: true });
      fs.writeFileSync(hashFile, hash);
    },
    configureServer(server) {
      server.watcher.add(files);
      server.watcher.on('change', (file) => {
        if (!files.includes(normalizePath(file))) return;
        clearTimeout(restartTimer);
        restartTimer = setTimeout(() => {
          server
            .restart(true)
            .catch((error: Error) => server.config.logger.error(error.stack ?? error.message));
        }, 100);
      });
    },
    closeBundle() {
      clearTimeout(restartTimer);
    },
  };
}
