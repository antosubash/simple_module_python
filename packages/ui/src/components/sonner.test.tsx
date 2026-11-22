import { act, render, waitFor } from '@testing-library/react';
import { toast } from 'sonner';
import { afterEach, expect, it } from 'vitest';
import { Toaster } from './ui/sonner';

afterEach(() => {
  toast.dismiss();
  document.documentElement.classList.remove('dark');
});

it('follows the document dark class, including changes after mounting', async () => {
  document.documentElement.classList.add('dark');
  const { container, unmount } = render(<Toaster />);
  await act(async () => {
    toast('Theme probe');
  });
  const theme = () =>
    container.querySelector('[data-sonner-toaster]')?.getAttribute('data-sonner-theme');
  await waitFor(() => expect(theme()).toBe('dark'));
  await act(async () => document.documentElement.classList.remove('dark'));
  await waitFor(() => expect(theme()).toBe('light'));
  await act(async () => document.documentElement.classList.add('dark'));
  await waitFor(() => expect(theme()).toBe('dark'));
  unmount();
});
