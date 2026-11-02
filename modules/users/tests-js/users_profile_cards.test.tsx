import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { toast } from 'sonner';
import { PasswordCard } from '../users/auth_local/components/PasswordCard';
import { SessionsCard } from '../users/auth_local/components/SessionsCard';
import { json, stubFetch } from './users_fixtures';

configureI18n({
  locale: 'en',
  messages: {
    'users.profile.toast_signed_out_failed': 'Could not sign out the other sessions',
    'users.profile.toast_password_failed': 'Could not change your password',
    'users.profile.sign_out_everywhere': 'Sign out everywhere',
    'users.profile.sign_out_confirm_action': 'Sign out',
    'users.profile.change_password': 'Change password',
  },
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('SessionsCard', () => {
  it('shows the translated failure on the card when sign-out everywhere is refused', async () => {
    stubFetch(() => json(401, { detail: 'Unauthorized' }));
    render(<SessionsCard lastLoginAt={null} />);
    fireEvent.click(screen.getByRole('button', { name: 'Sign out everywhere' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Sign out' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not sign out the other sessions',
    );
    expect(toast.error).toHaveBeenCalledWith('Could not sign out the other sessions');
  });
});

describe('PasswordCard', () => {
  it('shows the translated failure when the change is refused without a detail', async () => {
    stubFetch(() => json(401, {}));
    render(<PasswordCard />);
    const inputs = document.querySelectorAll('input');
    for (const input of inputs) {
      fireEvent.change(input, { target: { value: 'BrandNewPass1!' } });
    }
    fireEvent.submit(document.querySelector('form') as HTMLFormElement);
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Could not change your password'),
    );
    expect(toast.success).not.toHaveBeenCalled();
  });
});
