import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import type { Plugin } from 'vite';

/**
 * Emit `.gz` and `.br` siblings for built JS/CSS.
 *
 * The server (PrecompressedStaticFiles) serves these directly instead of
 * compressing the same immutable, content-hashed bundle on every request.
 * Two wins: no per-request compression CPU, and because this runs once at
 * build time it can afford the maximum compression level — on-the-fly
 * compression has to use a fast, worse one.
 *
 * Measured across this bundle: 996.5 KB raw -> 287.6 KB gzip-9 -> 248.5 KB
 * brotli-11. Brotli is ~14% smaller than gzip, which is why the server
 * prefers it when the client accepts it.
 *
 * Uses Node's built-in zlib, so this adds no dependency.
 */

// Matches COMPRESSION_MIN_BYTES in simple_module_hosting/_phase_helpers.py.
// Below this, the compressed framing costs more than it saves.
const MIN_BYTES = 500;
const COMPRESSIBLE = /\.(js|css|svg|json|map)$/;

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walk(full));
    else out.push(full);
  }
  return out;
}

export function compressAssets(): Plugin {
  let outDir = '';
  return {
    name: 'simple-module:compress-assets',
    // Build only — in dev, Vite serves modules from memory and there is
    // nothing on disk to pre-compress.
    apply: 'build',
    configResolved(config) {
      outDir = path.resolve(config.root, config.build.outDir);
    },
    closeBundle() {
      if (!outDir || !fs.existsSync(outDir)) return;
      let files = 0;
      let raw = 0;
      let gz = 0;
      let br = 0;

      for (const file of walk(outDir)) {
        if (!COMPRESSIBLE.test(file)) continue;
        const source = fs.readFileSync(file);
        if (source.length < MIN_BYTES) continue;

        const gzipped = zlib.gzipSync(source, { level: zlib.constants.Z_BEST_COMPRESSION });
        const brotlied = zlib.brotliCompressSync(source, {
          params: {
            [zlib.constants.BROTLI_PARAM_QUALITY]: zlib.constants.BROTLI_MAX_QUALITY,
            [zlib.constants.BROTLI_PARAM_SIZE_HINT]: source.length,
          },
        });

        // Only keep a variant that actually beats the original — a already
        // compressed asset (e.g. a pre-minified .map) can grow.
        if (gzipped.length < source.length) fs.writeFileSync(`${file}.gz`, gzipped);
        if (brotlied.length < source.length) fs.writeFileSync(`${file}.br`, brotlied);

        files += 1;
        raw += source.length;
        gz += gzipped.length;
        br += brotlied.length;
      }

      if (files === 0) return;
      const kb = (n: number) => `${(n / 1024).toFixed(1)} kB`;
      // eslint-disable-next-line no-console
      console.log(
        `\ncompress-assets: ${files} files  ${kb(raw)} raw  ` +
          `→ ${kb(gz)} gzip  →  ${kb(br)} brotli`,
      );
    },
  };
}
