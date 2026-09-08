/**
 * The reveal toggle, and the 44px tap target it hides behind.
 *
 * `PasswordStrength` was covered; this sibling was not, so neither the toggle
 * nor `max-lg:min-h-11` — the thing that makes the button reachable with a
 * thumb without making the field taller than every other input — was exercised.
 */
import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import { PasswordInput } from './PasswordInput';

const LABELS = { showLabel: 'Show', hideLabel: 'Hide' };

function renderInput() {
  render(<PasswordInput {...LABELS} aria-label="Password" defaultValue="hunter2" />);
  return {
    field: screen.getByLabelText('Password'),
    toggle: () => screen.getByRole('button'),
  };
}

describe('the reveal toggle', () => {
  test('it starts hidden, so a shoulder-surfer sees nothing by default', () => {
    const { field, toggle } = renderInput();

    expect(field).toHaveAttribute('type', 'password');
    expect(toggle()).toHaveTextContent('Show');
  });

  test('it reveals the value and offers to hide it again', async () => {
    const user = userEvent.setup();
    const { field, toggle } = renderInput();

    await user.click(toggle());
    expect(field).toHaveAttribute('type', 'text');
    // The label names what the next press will do, which is why it is a word
    // and not an eye icon — an eye does not say which state you are in.
    expect(toggle()).toHaveTextContent('Hide');

    await user.click(toggle());
    expect(field).toHaveAttribute('type', 'password');
    expect(toggle()).toHaveTextContent('Show');
  });

  test('it does not submit the form it sits in', () => {
    const { toggle } = renderInput();

    expect(toggle()).toHaveAttribute('type', 'button');
  });

  test('it keeps a 44px target on phones', () => {
    const { toggle } = renderInput();

    expect(toggle().className).toContain('max-lg:min-h-11');
  });
});

describe('what it passes through', () => {
  test('caller classes survive the internal padding class', () => {
    render(<PasswordInput {...LABELS} aria-label="Password" className="border-destructive" />);

    const field = screen.getByLabelText('Password');
    expect(field.className).toContain('border-destructive');
    // pr-16 keeps the typed value from running under the toggle.
    expect(field.className).toContain('pr-16');
  });

  test('arbitrary input props reach the field', () => {
    render(
      <PasswordInput {...LABELS} aria-label="Password" required autoComplete="new-password" />,
    );

    const field = screen.getByLabelText('Password');
    expect(field).toBeRequired();
    expect(field).toHaveAttribute('autocomplete', 'new-password');
  });
});
