import { fireEvent, render, screen } from '@testing-library/react';
import { Trash2 } from 'lucide-react';
import type React from 'react';
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

describe('ConfirmActionDialog', () => {
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

  test('disables confirm while the action is in flight', () => {
    renderDialog({ busy: true });
    expect(screen.getByRole('button', { name: 'Delete' })).toBeDisabled();
  });

  test('renders extra content between the description and the buttons', () => {
    renderDialog({ children: <p>flag: beta-search</p> });
    expect(screen.getByText('flag: beta-search')).toBeInTheDocument();
  });
});
