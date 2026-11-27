import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

// Vite 8.4's dependency optimiser (Rolldown 1.3) rejects a package that imports
// itself by name: the self-import becomes an external id for a file it already
// bundles (INVALID_EXTERNAL_ID, GH #1245). Shipped sources use relative imports.
const SRC = import.meta.dirname;
const SELF_IMPORT = /(?:from|import)\s*\(?\s*['"]@simple-module-py\/ui(?:\/[^'"]*)?['"]/;

function shippedSources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return shippedSources(full);
    return /\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name) ? [full] : [];
  });
}

describe('@simple-module-py/ui sources', () => {
  it('import the package itself only through relative paths', () => {
    const offenders = shippedSources(SRC).filter((file) =>
      SELF_IMPORT.test(readFileSync(file, 'utf-8')),
    );
    expect(offenders.map((file) => path.relative(SRC, file))).toEqual([]);
  });
});
