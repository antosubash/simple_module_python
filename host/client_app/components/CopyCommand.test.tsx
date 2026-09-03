import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, test, vi } from 'vitest';

// Mock @simple-module-py/i18n so useT resolves without a real i18next
// instance — same pattern AdminSectionLink.test.tsx uses.
vi.mock('@simple-module-py/i18n', () => ({
  useT: () => ({
    t: (key: string) =>
      ({
        'host.landing.copy_command': 'Copy command',
        'host.landing.copy_label': 'Copy',
        'host.landing.command_copied': '✓ Copied',
      })[key] ?? key,
  }),
  keys: {
    host: {
      landing: {
        copy_command: 'host.landing.copy_command',
        copy_label: 'host.landing.copy_label',
        command_copied: 'host.landing.command_copied',
      },
    },
  },
}));

import { CopyCommand } from './CopyCommand';

const COMMAND = 'uvx --from simple_module_cli smpy new my-app';

function stubClipboard(impl: () => Promise<void>) {
  const writeText = vi.fn(impl);
  Object.assign(navigator, { clipboard: { writeText } });
  return writeText;
}

/** Click, then let the awaited `writeText` settle before asserting. */
async function clickCopy() {
  fireEvent.click(screen.getByRole('button', { name: 'Copy command' }));
  await act(async () => {});
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('CopyCommand', () => {
  test('renders the command in full', () => {
    stubClipboard(() => Promise.resolve());
    render(<CopyCommand command={COMMAND} />);
    // The whole string, not an ellipsised prefix — the markup this replaced
    // `truncate`d it, hiding 107px of it at 375px with no way to reveal it.
    expect(screen.getByText(COMMAND)).toBeInTheDocument();
  });

  // The regression this file exists for: the button shipped with an
  // aria-label promising an action and no handler at all, so it was inert
  // while asserting otherwise. Nothing caught it.
  test('writes the command to the clipboard when clicked', async () => {
    const writeText = stubClipboard(() => Promise.resolve());
    render(<CopyCommand command={COMMAND} />);

    await clickCopy();

    expect(writeText).toHaveBeenCalledTimes(1);
    expect(writeText).toHaveBeenCalledWith(COMMAND);
  });

  // The deck labels the control in words, not an icon: a bare glyph on a
  // dark strip reads as decoration, and this is the one action the hero has.
  test('labels the control "Copy" before anything is copied', () => {
    stubClipboard(() => Promise.resolve());
    render(<CopyCommand command={COMMAND} />);

    expect(screen.getByRole('button', { name: 'Copy command' })).toHaveTextContent('Copy');
    expect(screen.queryByText('✓ Copied')).not.toBeInTheDocument();
  });

  test('swaps the visible label to "✓ Copied" after a click', async () => {
    stubClipboard(() => Promise.resolve());
    render(<CopyCommand command={COMMAND} />);

    await clickCopy();

    expect(screen.getByText('✓ Copied')).toBeInTheDocument();
  });

  test('clears the announcement after the reset window', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    stubClipboard(() => Promise.resolve());
    render(<CopyCommand command={COMMAND} />);

    await clickCopy();
    expect(screen.getByText('✓ Copied')).toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(2000);
    });

    expect(screen.queryByText('✓ Copied')).not.toBeInTheDocument();
    expect(screen.getByText('Copy')).toBeInTheDocument();
  });

  test('stays quiet when the clipboard is unavailable', async () => {
    // Insecure origins and permission policy both reject writeText. The
    // command is on screen and selectable, so a rejection is not worth an
    // error state — but it must not claim success either.
    stubClipboard(() => Promise.reject(new Error('denied')));
    render(<CopyCommand command={COMMAND} />);

    await clickCopy();

    expect(screen.queryByText('✓ Copied')).not.toBeInTheDocument();
  });
});
