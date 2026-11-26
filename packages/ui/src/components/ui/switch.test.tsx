import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test } from 'vitest';
import { Switch } from './switch';

test('a touch-sized switch remains operable by pointer and keyboard', async () => {
  const user = userEvent.setup();
  const { rerender } = render(<Switch aria-label="Feature" />);
  const control = screen.getByRole('switch', { name: 'Feature' });
  expect(control).toHaveClass(
    'max-lg:min-h-11',
    'max-lg:min-w-11',
    'pointer-coarse:min-h-11',
    'pointer-coarse:min-w-11',
  );
  await user.click(control);
  expect(control).toBeChecked();
  await user.keyboard(' ');
  expect(control).not.toBeChecked();
  rerender(<Switch aria-label="Feature" disabled />);
  await user.click(control);
  expect(control).not.toBeChecked();
});
