/**
 * Fail CI when a `.tsx` file renders user-visible text as a literal instead of
 * routing it through `t(keys.…)`.
 *
 * Detection lives in ./lib/untranslated-strings.mjs (unit-tested); this file is
 * the CLI around it — which files to read, and how to report.
 *
 * Usage:
 *   node scripts/check_untranslated_strings.mjs           # fail on findings
 *   node scripts/check_untranslated_strings.mjs --list    # report only
 */

import { globSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { argv, cwd, exit } from 'node:process';
import { findUntranslated } from './lib/untranslated-strings.mjs';

const ROOT = cwd();

/** Everything whose rendered text a user can read. */
const INCLUDE = ['modules/*/*/**/*.tsx', 'packages/ui/src/**/*.tsx', 'host/client_app/**/*.tsx'];

/**
 * Vendored shadcn primitives are upstream code we re-sync, so their few
 * literals are not ours to edit; tests and stories render fixtures, not copy.
 */
const EXCLUDE = [/packages\/ui\/src\/components\/ui\//, /\.test\.tsx$/, /\.stories\.tsx$/];

function sourceFiles() {
  const seen = new Set();
  for (const pattern of INCLUDE) {
    for (const match of globSync(pattern, { cwd: ROOT })) {
      const rel = match.split('\\').join('/');
      if (!EXCLUDE.some((re) => re.test(rel))) seen.add(rel);
    }
  }
  return [...seen].sort();
}

const listOnly = argv.includes('--list');
const findings = sourceFiles().flatMap((rel) =>
  findUntranslated(readFileSync(resolve(ROOT, rel), 'utf8')).map((f) => ({ ...f, file: rel })),
);

if (findings.length === 0) {
  console.log('OK: no untranslated user-visible strings found.');
  exit(0);
}

const byFile = new Map();
for (const finding of findings) {
  if (!byFile.has(finding.file)) byFile.set(finding.file, []);
  byFile.get(finding.file).push(finding);
}

console.log(
  listOnly
    ? `${findings.length} user-visible literal(s):\n`
    : `FAIL: ${findings.length} untranslated user-visible string(s):\n`,
);
for (const [file, items] of byFile) {
  console.log(`  ${file}`);
  for (const item of items) console.log(`    ${item.line}: [${item.kind}] ${item.value}`);
  console.log('');
}

if (!listOnly) {
  console.log(
    'Route these through t(keys.<namespace>.…) from @simple-module-py/i18n, add the\n' +
      "key to the module's locales/en.json, then regenerate the key union.\n" +
      'For a genuinely technical literal — a shell command, an env var name, a JSON\n' +
      'example — wrap it in <code>/<pre>, or mark the line `// i18n-exempt: <reason>`.',
  );
}

exit(listOnly ? 0 : 1);
