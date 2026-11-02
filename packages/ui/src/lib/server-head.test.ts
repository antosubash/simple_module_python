import { describe, expect, test } from 'vitest';
import { resolveServerHead } from './server-head';

describe('resolveServerHead', () => {
  test('returns the _head tags', () => {
    const tags = ['<title data-inertia="">A</title>', '<meta data-inertia="x" name="a">'];
    expect(resolveServerHead({ props: { _head: tags } })).toEqual(tags);
  });

  test('is empty when the page sent no head', () => {
    expect(resolveServerHead({ props: {} })).toEqual([]);
    expect(resolveServerHead({})).toEqual([]);
  });

  test('ignores a malformed prop and non-string entries', () => {
    expect(resolveServerHead({ props: { _head: 'nope' } })).toEqual([]);
    expect(resolveServerHead({ props: { _head: ['<meta>', 3, null] } })).toEqual(['<meta>']);
  });
});
