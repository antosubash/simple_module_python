import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';

configureI18n({
  locale: 'en',
  messages: {
    'users.linked_sign_ins.title': 'Linked sign-ins',
    'users.linked_sign_ins.subject': 'Subject',
    'users.linked_sign_ins.last_sign_in': 'Last signed in {when}',
    'users.linked_sign_ins.never': 'Not signed in through it yet',
  },
});

import { LinkedSignInsCard } from '../users/pages/Users/components/LinkedSignInsCard';

describe('LinkedSignInsCard', () => {
  test('lists each provider with its username, subject and last sign-in', () => {
    render(
      <LinkedSignInsCard
        links={[
          {
            provider: 'Microsoft',
            username: 'jane@corp.com',
            subject: 'pairwise-sub',
            last_sign_in_at: new Date().toISOString(),
          },
          { provider: 'GitHub', username: null, subject: null, last_sign_in_at: null },
        ]}
      />,
    );
    expect(screen.getByText('Linked sign-ins')).toBeInTheDocument();
    expect(screen.getByText('Microsoft')).toBeInTheDocument();
    expect(screen.getByText(/jane@corp\.com/)).toBeInTheDocument();
    expect(screen.getByText('pairwise-sub')).toBeInTheDocument();
    expect(screen.getByText(/^Last signed in/)).toBeInTheDocument();
    expect(screen.getByText('Not signed in through it yet')).toBeInTheDocument();
  });
});
