import { globSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/** Every page rendered in AdminLayout sets a document title (#422: /admin/users/ had none). */
const ROOT = join(__dirname, '..', '..');
const files = globSync('modules/*/*/pages/**/*.tsx', { cwd: ROOT })
  .filter((f) => !f.endsWith('.test.tsx'))
  .map((f) => join(ROOT, f))
  .filter((f) => /\.layout\s*=\s*\[\s*AdminLayout/.test(readFileSync(f, 'utf8')));

describe('admin pages', () => {
  it('found some', () => expect(files.length).toBeGreaterThan(5));
  it.each(files)('%s renders <Head title>', (file) => {
    expect(readFileSync(file, 'utf8')).toMatch(/<Head\s[^>]*title=/);
  });
});
