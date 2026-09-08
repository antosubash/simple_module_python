import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

configureI18n({
  locale: 'en',
  messages: {
    'users.invite_fields.chip_placeholder': 'Paste a list, or type and press Enter…',
    'users.invite_fields.remove_chip': 'Remove {email}',
    'users.invite_fields.counter': '{count} addresses · {invalid} invalid',
    'users.invite_fields.counter_clean': '{count} addresses',
  },
});

import { EmailChipInput } from '../users/pages/Users/components/EmailChipInput';

function field(): HTMLElement {
  return screen.getByRole('textbox');
}

function typeAndPress(text: string, key: string) {
  fireEvent.change(field(), { target: { value: text } });
  fireEvent.keyDown(field(), { key });
}

describe('EmailChipInput', () => {
  test('Enter turns the typed address into a chip', () => {
    const onChange = vi.fn();
    render(<EmailChipInput value={[]} onChange={onChange} />);
    typeAndPress('rob@example.com', 'Enter');
    expect(onChange).toHaveBeenCalledWith(['rob@example.com']);
  });

  test('a comma commits the address too', () => {
    const onChange = vi.fn();
    render(<EmailChipInput value={[]} onChange={onChange} />);
    typeAndPress('nia@example.com', ',');
    expect(onChange).toHaveBeenCalledWith(['nia@example.com']);
  });

  test('an invalid chip is flagged rather than dropped', () => {
    render(<EmailChipInput value={['rob@example.com', 'not-an-email']} onChange={vi.fn()} />);
    expect(screen.getByText('not-an-email')).toHaveAttribute('data-valid', 'false');
    expect(screen.getByText('rob@example.com')).toHaveAttribute('data-valid', 'true');
  });

  test('the counter reports the total and the invalid share', () => {
    render(
      <EmailChipInput
        value={['rob@example.com', 'nia@example.com', 'not-an-email']}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText('3 addresses · 1 invalid')).toBeInTheDocument();
  });

  test('the counter drops the invalid clause when every address is fine', () => {
    render(<EmailChipInput value={['rob@example.com']} onChange={vi.fn()} />);
    expect(screen.getByText('1 addresses')).toBeInTheDocument();
  });

  test('pasting splits on commas and whitespace', () => {
    const onChange = vi.fn();
    render(<EmailChipInput value={[]} onChange={onChange} />);
    fireEvent.paste(field(), {
      clipboardData: { getData: () => 'a@example.com, b@example.com\nc@example.com' },
    });
    expect(onChange).toHaveBeenCalledWith(['a@example.com', 'b@example.com', 'c@example.com']);
  });

  test('a repeated address is added once', () => {
    const onChange = vi.fn();
    render(<EmailChipInput value={['rob@example.com']} onChange={onChange} />);
    typeAndPress('rob@example.com', 'Enter');
    expect(onChange).not.toHaveBeenCalled();
  });

  test('backspace on an empty field removes the last chip', () => {
    const onChange = vi.fn();
    render(<EmailChipInput value={['a@example.com', 'b@example.com']} onChange={onChange} />);
    fireEvent.keyDown(field(), { key: 'Backspace' });
    expect(onChange).toHaveBeenCalledWith(['a@example.com']);
  });

  test('backspace mid-word leaves the chips alone', () => {
    const onChange = vi.fn();
    render(<EmailChipInput value={['a@example.com']} onChange={onChange} />);
    fireEvent.change(field(), { target: { value: 'partial' } });
    fireEvent.keyDown(field(), { key: 'Backspace' });
    expect(onChange).not.toHaveBeenCalled();
  });

  test('the remove button drops just that chip', () => {
    const onChange = vi.fn();
    render(<EmailChipInput value={['a@example.com', 'b@example.com']} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: 'Remove a@example.com' }));
    expect(onChange).toHaveBeenCalledWith(['b@example.com']);
  });

  test('leaving the field commits whatever was typed', () => {
    const onChange = vi.fn();
    render(<EmailChipInput value={[]} onChange={onChange} />);
    fireEvent.change(field(), { target: { value: 'late@example.com' } });
    fireEvent.blur(field());
    expect(onChange).toHaveBeenCalledWith(['late@example.com']);
  });
});
