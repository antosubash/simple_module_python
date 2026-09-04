import { describe, expect, it } from 'vitest';
import { initials } from './initials';

describe('initials', () => {
  it('takes the first and last word of a full name', () => {
    expect(initials('Dana Rivera')).toBe('DR');
    expect(initials('ada b. lovelace')).toBe('AL');
  });

  it('takes the first two letters of a single-word name', () => {
    expect(initials('admin')).toBe('AD');
  });

  it('falls back to the email local part when there is no name', () => {
    expect(initials(null, 'rob@example.com')).toBe('RO');
    expect(initials('   ', 'rob@example.com')).toBe('RO');
  });

  it('prefers the name over the email', () => {
    expect(initials('Dana Rivera', 'rob@example.com')).toBe('DR');
  });

  it('returns a placeholder when there is nothing to work with', () => {
    expect(initials()).toBe('?');
    expect(initials(null, null)).toBe('?');
    expect(initials('', '')).toBe('?');
  });

  it('copes with a one-character source', () => {
    expect(initials('x')).toBe('X');
    expect(initials(null, 'r@example.com')).toBe('R');
  });
});
