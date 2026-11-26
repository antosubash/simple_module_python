import { configureI18n, keys } from '@simple-module-py/i18n';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';
import { AccountCard } from '../users/pages/Users/components/AccountCard';
import { DangerZone } from '../users/pages/Users/components/DangerZone';

vi.mock('@inertiajs/react', () => ({ router: { visit: vi.fn() } }));
configureI18n({ locale: 'en', messages: {} });

test.each(['delete', 'disable', 'reset'])(
  '%s dialog restores its opener after Cancel and Escape, including reopening',
  async (action) => {
    const user = userEvent.setup();
    render(
      action === 'delete' ? (
        <DangerZone userId="target" email="alice@example.com" isSelf={false} />
      ) : (
        <AccountCard
          email="alice@example.com"
          isExternal={false}
          createdAt={null}
          disabledAt={null}
          isActive
          isVerified
          lockedUntil={null}
          savingStatus={false}
          savingVerify={false}
          onDisable={() => {}}
          onEnable={() => {}}
          onMarkVerified={() => {}}
          onCopyResetLink={() => {}}
        />
      ),
    );
    const opener = screen.getByRole('button', {
      name:
        action === 'delete'
          ? keys.users.danger_zone.delete_button
          : action === 'disable'
            ? keys.users.account_status.disable_button
            : keys.users.account_status.copy_reset_link,
    });
    for (const dismiss of ['cancel', 'escape']) {
      await user.click(opener);
      expect(screen.getByRole('alertdialog')).toBeInTheDocument();
      if (dismiss === 'cancel')
        await user.click(screen.getByRole('button', { name: keys.users.common.cancel }));
      else await user.keyboard('{Escape}');
      await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
      await waitFor(() => expect(opener).toHaveFocus());
    }
  },
);
