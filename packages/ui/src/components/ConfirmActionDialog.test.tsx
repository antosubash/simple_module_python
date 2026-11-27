import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Trash2 } from 'lucide-react';
import type React from 'react';
import { useState } from 'react';
import { describe, expect, test, vi } from 'vitest';

import { ConfirmActionDialog } from './ConfirmActionDialog';

function renderDialog(props: Partial<React.ComponentProps<typeof ConfirmActionDialog>> = {}) {
  const onConfirm = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <ConfirmActionDialog
      open
      onOpenChange={onOpenChange}
      icon={Trash2}
      title="Delete project"
      description="This removes every dataset it holds."
      confirmLabel="Delete"
      cancelLabel="Cancel"
      onConfirm={onConfirm}
      {...props}
    />,
  );
  return { onConfirm, onOpenChange };
}

function FocusDialog({
  onCloseAutoFocus,
  removeOpener = false,
  disableOpener = false,
}: {
  onCloseAutoFocus?: React.ComponentProps<typeof ConfirmActionDialog>['onCloseAutoFocus'];
  removeOpener?: boolean;
  disableOpener?: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      {!removeOpener && (
        <button type="button" disabled={disableOpener} onClick={() => setOpen(true)}>
          Open confirmation
        </button>
      )}
      <button type="button" onClick={() => setOpen(true)}>
        Focus destination
      </button>
      <ConfirmActionDialog
        open={open}
        onOpenChange={setOpen}
        onCloseAutoFocus={onCloseAutoFocus}
        icon={Trash2}
        title="Delete project"
        description="This removes every dataset it holds."
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onConfirm={() => {}}
      />
    </>
  );
}

function openConfirmation() {
  const opener = screen.getByRole('button', { name: 'Open confirmation' });
  opener.focus();
  fireEvent.click(opener);
  expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus();
  return opener;
}

describe('ConfirmActionDialog', () => {
  test.each(['Escape', 'Cancel', 'Delete'])(
    'returns focus to the opener after %s',
    async (action) => {
      render(<FocusDialog />);
      const opener = openConfirmation();
      if (action === 'Escape') {
        fireEvent.keyDown(screen.getByRole('alertdialog'), { key: 'Escape' });
      } else {
        fireEvent.click(screen.getByRole('button', { name: action }));
      }
      await waitFor(() => expect(opener).toHaveFocus());
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    },
  );

  test('lets a caller preventing close autofocus choose the focus destination', async () => {
    render(
      <FocusDialog
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          screen.getByRole('button', { name: 'Focus destination' }).focus();
        }}
      />,
    );
    openConfirmation();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Focus destination' })).toHaveFocus(),
    );
  });

  test('restores the opener when the caller does not prevent close autofocus', async () => {
    const onCloseAutoFocus = vi.fn();
    render(<FocusDialog onCloseAutoFocus={onCloseAutoFocus} />);
    const opener = openConfirmation();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(opener).toHaveFocus());
    expect(onCloseAutoFocus).toHaveBeenCalledTimes(1);
  });

  test('remembers the current opener on each opening', async () => {
    render(<FocusDialog />);
    const firstOpener = openConfirmation();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(firstOpener).toHaveFocus());
    const nextOpener = screen.getByRole('button', { name: 'Focus destination' });
    nextOpener.focus();
    fireEvent.click(nextOpener);
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(nextOpener).toHaveFocus());
  });

  test.each(['removed', 'disabled'])('closes safely when the opener is %s', async (state) => {
    const onCloseAutoFocus = vi.fn();
    const { rerender } = render(<FocusDialog onCloseAutoFocus={onCloseAutoFocus} />);
    const opener = openConfirmation();
    rerender(
      <FocusDialog
        onCloseAutoFocus={onCloseAutoFocus}
        removeOpener={state === 'removed'}
        disableOpener={state === 'disabled'}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(onCloseAutoFocus).toHaveBeenCalledTimes(1));
    expect(document.body).toHaveFocus();
    expect(opener).not.toHaveFocus();
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  test('shows the title, description and both buttons when open', () => {
    renderDialog();
    expect(screen.getByText('Delete project')).toBeInTheDocument();
    expect(screen.getByText('This removes every dataset it holds.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
  });

  test('renders nothing while closed', () => {
    renderDialog({ open: false });
    expect(screen.queryByText('Delete project')).not.toBeInTheDocument();
  });

  test('confirms straight away when no typed confirmation is required', () => {
    const { onConfirm } = renderDialog();
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  test('holds the confirm button disabled until the expected text is typed', () => {
    const { onConfirm } = renderDialog({
      confirmText: { expected: 'atlas', label: 'Type atlas to confirm' },
    });
    const confirm = screen.getByRole('button', { name: 'Delete' });
    expect(confirm).toBeDisabled();

    const input = screen.getByLabelText('Type atlas to confirm');
    fireEvent.change(input, { target: { value: 'atl' } });
    expect(confirm).toBeDisabled();

    fireEvent.change(input, { target: { value: 'ATLAS' } });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  test('gives both footer buttons a 44px phone hit target', () => {
    renderDialog();
    expect(screen.getByRole('button', { name: 'Delete' })).toHaveClass('max-lg:min-h-11');
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveClass('max-lg:min-h-11');
  });

  test('disables confirm while the action is in flight', () => {
    renderDialog({ busy: true });
    expect(screen.getByRole('button', { name: 'Delete' })).toBeDisabled();
  });

  test('a caller tracking busy is left to close the dialog itself', () => {
    // The whole point of `busy`: Radix closes on click, and a dialog that
    // vanishes mid-request looks like the request finished.
    const { onConfirm, onOpenChange } = renderDialog({ busy: false });
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  test('a caller that never mentions busy still gets an auto-close', () => {
    const { onConfirm, onOpenChange } = renderDialog();
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  test('renders extra content between the description and the buttons', () => {
    renderDialog({ children: <p>flag: beta-search</p> });
    expect(screen.getByText('flag: beta-search')).toBeInTheDocument();
  });
});
