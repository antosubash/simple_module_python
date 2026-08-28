import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

configureI18n({
  locale: 'en',
  messages: {
    'users.invite_fields.invalid_email_one': '{email} is not a valid email address.',
    'users.invite_fields.invalid_email_other': '{count} addresses are not valid email addresses.',
  },
});

import { InviteFields } from '../users/pages/Users/components/InviteFields';
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

  test('warns about an invalid address before submit', () => {
    render(
      <InviteFields
        emails="not-an-email"
        onEmailsChange={vi.fn()}
        count={0}
        invalidEmails={['not-an-email']}
        mailerDelivers
      />,
    );

    expect(screen.getByRole('alert')).toHaveTextContent(
      'not-an-email is not a valid email address.',
    );
  });
});
