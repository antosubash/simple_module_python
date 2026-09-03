import { describe, expect, test } from 'vitest';

import { isPlausibleEmail, parseInviteEmails } from '../users/pages/Users/invite-emails';

describe('invite email validation', () => {
  test('parses pasted addresses using every supported separator', () => {
    expect(parseInviteEmails('one@example.com; two@example.com\nthree@example.com')).toEqual([
      'one@example.com',
      'two@example.com',
      'three@example.com',
    ]);
  });

  test.each([
    ['teammate@example.com', true],
    ['not-an-email', false],
    ['missing-domain@', false],
    ['missing-tld@example', false],
  ])('classifies %s', (email, expected) => {
    expect(isPlausibleEmail(email)).toBe(expected);
  });
});
