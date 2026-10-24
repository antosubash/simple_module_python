import { router } from '@inertiajs/react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { CommandPalette } from './CommandPalette';

vi.mock('@inertiajs/react', () => ({ router: { visit: vi.fn(), post: vi.fn() } }));
vi.mock('@simple-module-py/i18n', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@simple-module-py/i18n')>()),
  useT: () => ({ t: (key: string) => key }),
}));

beforeAll(() => {
  // cmdk scrolls the selected result; jsdom has no layout or scrollIntoView.
  HTMLElement.prototype.scrollIntoView = vi.fn();
});
afterEach(() => vi.resetAllMocks());

function setup() {
  const view = render(
    <>
      <button type="button">Before</button>
      <CommandPalette
        navItems={[{ label: 'Dashboard', url: '/dashboard', icon: 'grid' }]}
        accountItems={[{ label: 'Logout', url: '/logout', icon: 'log-out', method: 'post' }]}
      />
      <button type="button">After</button>
    </>,
  );
  return {
    ...view,
    user: userEvent.setup(),
    search: screen.getByRole('button', { name: /trigger/ }),
  };
}

async function expectClosedWithFocus(target: HTMLElement) {
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  await waitFor(() => expect(target).toHaveFocus());
}

describe('CommandPalette focus', () => {
  it.each(['Escape', 'Close', 'overlay', 'Control+k', 'Meta+k'])(
    'restores Search after dismissal with %s and continues tab order',
    async (dismiss) => {
      const { user, search } = setup();
      await user.tab();
      await user.tab();
      expect(search).toHaveFocus();
      await user.keyboard('{Enter}');
      expect(screen.getByRole('combobox')).toHaveFocus();

      if (dismiss === 'Close') await user.click(screen.getByRole('button', { name: 'Close' }));
      else if (dismiss === 'overlay') {
        const overlay = document.querySelector('[data-slot="dialog-overlay"]');
        if (!overlay) throw new Error('Missing dialog overlay');
        await user.click(overlay);
      } else if (dismiss === 'Escape') await user.keyboard('{Escape}');
      else await user.keyboard(`{${dismiss.split('+')[0]}>}k{/${dismiss.split('+')[0]}}`);

      await expectClosedWithFocus(search);
      await user.tab();
      expect(screen.getByRole('button', { name: 'After' })).toHaveFocus();
    },
  );

  it.each(['Control', 'Meta'])(
    'restores the previous element after opening with %s+k',
    async (key) => {
      const { user } = setup();
      const before = screen.getByRole('button', { name: 'Before' });
      before.focus();
      await user.keyboard(`{${key}>}k{/${key}}`);
      expect(screen.getByRole('combobox')).toHaveFocus();
      await user.keyboard('{Escape}');
      await expectClosedWithFocus(before);
    },
  );

  it.each(['Dashboard', 'Logout'])('does not restore focus after selecting %s', async (label) => {
    const { user, search } = setup();
    await user.click(search);
    const restore = vi.spyOn(search, 'focus');
    await user.click(screen.getByRole('option', { name: label }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    // Radix schedules close autofocus after unmount.
    await act(() => new Promise((resolve) => setTimeout(resolve, 10)));
    expect(restore).not.toHaveBeenCalled();
    expect(label === 'Logout' ? router.post : router.visit).toHaveBeenCalledWith(
      label === 'Logout' ? '/logout' : '/dashboard',
    );
    restore.mockRestore();

    // A later dismissal must capture a fresh opener after navigation.
    await user.click(search);
    await user.keyboard('{Escape}');
    await expectClosedWithFocus(search);
  });

  it('ignores a disconnected opener', async () => {
    const { user, container } = setup();
    const before = screen.getByRole('button', { name: 'Before' });
    before.focus();
    await user.keyboard('{Control>}k{/Control}');
    const restore = vi.spyOn(before, 'focus');
    container.removeChild(before);
    await user.keyboard('{Escape}');
    await expectClosedWithFocus(document.body);
    expect(restore).not.toHaveBeenCalled();
    restore.mockRestore();
    container.prepend(before);
  });

  it('does not restore an external opener when the palette unmounts', async () => {
    const { user, rerender } = setup();
    const before = screen.getByRole('button', { name: 'Before' });
    before.focus();
    await user.keyboard('{Control>}k{/Control}');
    const restore = vi.spyOn(before, 'focus');
    rerender(<button type="button">Before</button>);
    await act(() => new Promise((resolve) => setTimeout(resolve, 10)));
    expect(before.isConnected).toBe(true);
    expect(restore).not.toHaveBeenCalled();
    restore.mockRestore();
    fireEvent.keyDown(document, { key: 'k', ctrlKey: true });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
