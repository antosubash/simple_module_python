import { describe, expect, it } from 'vitest';
import { scorePassword } from './PasswordStrength';

// The meter is a promise about how hard the password is to guess, so the
// scoring rule is the part worth pinning down — the bar is just its picture.
describe('scorePassword', () => {
  it('scores an empty password as nothing at all', () => {
    expect(scorePassword('')).toEqual({ level: 'none', percent: 0 });
  });

  it('scores anything under eight characters as weak', () => {
    expect(scorePassword('abc')).toEqual({ level: 'weak', percent: 33 });
    expect(scorePassword('Aa1!Aa1')).toEqual({ level: 'weak', percent: 33 });
  });

  it('scores an all-digit password as weak however long it is', () => {
    expect(scorePassword('1234567890123456')).toEqual({ level: 'weak', percent: 33 });
  });

  it('scores eight or more characters mixing letters and digits as ok', () => {
    expect(scorePassword('password1')).toEqual({ level: 'ok', percent: 66 });
    expect(scorePassword('abcdefg12')).toEqual({ level: 'ok', percent: 66 });
  });

  it('scores twelve or more characters over three character classes as strong', () => {
    expect(scorePassword('Password1234')).toEqual({ level: 'strong', percent: 100 });
    expect(scorePassword('correct-horse1')).toEqual({ level: 'strong', percent: 100 });
  });

  it('does not reward length alone', () => {
    expect(scorePassword('abcdefghijklmnop')).toEqual({ level: 'weak', percent: 33 });
  });
});
