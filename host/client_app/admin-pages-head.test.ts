import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/** Every page rendered in AdminLayout sets a document title (#422: /admin/users/ had none). */
function pagesUnder(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return pagesUnder(path);
    return name.endsWith('.tsx') && !name.endsWith('.test.tsx') ? [path] : [];
  });
}

const ROOT = join(__dirname, '..', '..');
const moduleDirs = readdirSync(join(ROOT, 'modules')).map((m) =>
  join(ROOT, 'modules', m, m, 'pages'),
);
const files = moduleDirs
  .filter((d) => {
    try {
      return statSync(d).isDirectory();
    } catch {
      return false;
    }
  })
  .flatMap(pagesUnder)
  .filter((f) => /\.layout\s*=\s*\[\s*AdminLayout/.test(readFileSync(f, 'utf8')));

describe('admin pages', () => {
  it('found some', () => expect(files.length).toBeGreaterThan(5));
  it.each(files)('%s renders <Head title>', (file) => {
    expect(readFileSync(file, 'utf8')).toMatch(/<Head\s[^>]*title=/);
  });
});
