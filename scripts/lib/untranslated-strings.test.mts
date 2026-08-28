import { describe, expect, it } from 'vitest';
// @ts-expect-error — plain .mjs helper, no type declarations by design.
import { findUntranslated } from './untranslated-strings.mjs';

const kinds = (source: string) => findUntranslated(source).map((f: { kind: string }) => f.kind);
const values = (source: string) => findUntranslated(source).map((f: { value: string }) => f.value);

describe('findUntranslated', () => {
  it('flags bare JSX text', () => {
    expect(values('const A = () => <p>Save changes</p>;')).toEqual(['Save changes']);
  });

  it('accepts text routed through t()', () => {
    expect(findUntranslated('const A = () => <p>{t(keys.a.b)}</p>;')).toEqual([]);
  });

  it('flags user-visible attributes but not machine ones', () => {
    const source = `const A = () => (
      <Input placeholder="Search by name" className="w-full" variant="outline" type="text" />
    );`;
    expect(kinds(source)).toEqual(['attr:placeholder']);
  });

  it('flags copy hidden in a conditional', () => {
    const source = "const A = () => <b aria-label={open ? 'Close menu' : 'Open menu'} />;";
    expect(kinds(source)).toEqual(['attr:aria-label']);
  });

  it('flags a literal toast argument', () => {
    const source = "function f() { toast.success('Profile updated'); }";
    expect(values(source)).toEqual(['Profile updated']);
  });

  it('ignores a toast argument that is translated', () => {
    expect(findUntranslated('function f() { toast.success(t(keys.a.b)); }')).toEqual([]);
  });

  it('leaves technical literals inside <code> alone', () => {
    const source = 'const A = () => <code>make doctor</code>;';
    expect(findUntranslated(source)).toEqual([]);
  });

  it('ignores punctuation, numbers, and single characters', () => {
    // "—" is an empty-value dash; "S" is an avatar initial fallback.
    const source = "const A = () => <><span>—</span><span>{name[0] ?? 'S'}</span></>;";
    expect(findUntranslated(source)).toEqual([]);
  });

  it('honours an i18n-exempt marker on the line above', () => {
    const source = ['const A = () => (', '  // i18n-exempt: a shell command', '  <p>make dev</p>', ');'].join(
      '\n',
    );
    expect(findUntranslated(source)).toEqual([]);
  });

  it('honours a file-level exemption', () => {
    const source = '/* i18n-exempt-file: fixture */\nconst A = () => <p>Demo copy</p>;';
    expect(findUntranslated(source)).toEqual([]);
  });

  it('does not mistake a type annotation for JSX text', () => {
    const source = 'type P = { onFiles: (f: FileList) => Promise<{ uploaded: number }> };';
    expect(findUntranslated(source)).toEqual([]);
  });

  it('fails closed on an unparseable file', () => {
    expect(kinds('const A = (((;')).toEqual(['parse-error']);
  });
});
