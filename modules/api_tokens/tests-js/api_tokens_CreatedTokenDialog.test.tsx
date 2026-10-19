import { configureI18n, keys } from '@simple-module-py/i18n';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

configureI18n({ locale: 'en', messages: {} });

import { CreatedTokenDialog } from '../api_tokens/pages/components/CreatedTokenDialog';

const SECRET = 'smpy_pat_0123456789abcdef';
const c = keys.api_tokens.created;

function stubClipboard(writeText: ReturnType<typeof vi.fn>) {
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
}

describe('CreatedTokenDialog', () => {
  beforeEach(() => stubClipboard(vi.fn().mockResolvedValue(undefined)));
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders nothing while there is no token', () => {
    render(<CreatedTokenDialog token={null} onClose={vi.fn()} />);
    expect(screen.queryByText(c.title)).toBeNull();
  });

  it('shows the secret with the one-time warning', () => {
    render(<CreatedTokenDialog token={SECRET} onClose={vi.fn()} />);
    expect(screen.getByText(SECRET)).toBeInTheDocument();
    expect(screen.getByText(c.warning)).toBeInTheDocument();
  });

  it('copies the secret to the clipboard and acknowledges it', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    stubClipboard(writeText);
    render(<CreatedTokenDialog token={SECRET} onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: c.copy }));
    await waitFor(() => expect(screen.getByRole('button', { name: c.copied })).toBeInTheDocument());
    expect(writeText).toHaveBeenCalledWith(SECRET);
  });

  it('survives a rejected clipboard and keeps offering Copy', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('denied'));
    stubClipboard(writeText);
    render(<CreatedTokenDialog token={SECRET} onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: c.copy }));
    await waitFor(() => expect(writeText).toHaveBeenCalled());
    expect(screen.getByRole('button', { name: c.copy })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: c.copied })).toBeNull();
    expect(screen.getByText(SECRET)).toBeInTheDocument();
  });

  it('closes through Done', () => {
    const onClose = vi.fn();
    render(<CreatedTokenDialog token={SECRET} onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: c.done }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('forgets the copied state after being closed and reopened', async () => {
    const { rerender } = render(<CreatedTokenDialog token={SECRET} onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: c.copy }));
    await waitFor(() => expect(screen.getByRole('button', { name: c.copied })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: c.done }));
    rerender(<CreatedTokenDialog token={null} onClose={vi.fn()} />);
    rerender(<CreatedTokenDialog token={SECRET} onClose={vi.fn()} />);
    expect(screen.getByRole('button', { name: c.copy })).toBeInTheDocument();
  });
});
