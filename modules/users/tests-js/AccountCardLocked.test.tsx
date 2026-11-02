import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

configureI18n({
  locale: 'en',
  messages: {
    'users.metadata_card.locked_until': 'Locked until',
    'users.account_status.unlock_button': 'Unlock',
  },
});

import { AccountCard } from '../users/pages/Users/components/AccountCard';

const base = {
  email: 'alice@example.com',
  isExternal: false,
  createdAt: '2026-01-01T00:00:00Z',
  disabledAt: null,
  isActive: true,
  isVerified: true,
  savingStatus: false,
  savingVerify: false,
  onDisable: () => {},
  onEnable: () => {},
  onMarkVerified: () => {},
  onCopyResetLink: () => {},
};

describe('AccountCard lockout', () => {
  test('a locked account shows when the lock lifts and an Unlock action', () => {
    const onUnlock = vi.fn();
    render(<AccountCard {...base} lockedUntil="2026-10-19T12:30:00Z" onUnlock={onUnlock} />);
    expect(screen.getByText('Locked until')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Unlock' }));
    expect(onUnlock).toHaveBeenCalledTimes(1);
  });

  test('an unlocked account shows neither', () => {
    render(<AccountCard {...base} lockedUntil={null} />);
    expect(screen.queryByText('Locked until')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Unlock' })).not.toBeInTheDocument();
  });

  test('Unlock is disabled while a status change is saving', () => {
    render(<AccountCard {...base} lockedUntil="2026-10-19T12:30:00Z" savingStatus />);
    expect(screen.getByRole('button', { name: 'Unlock' })).toBeDisabled();
  });
});
