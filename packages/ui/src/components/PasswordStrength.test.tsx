import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PasswordStrength } from './PasswordStrength';

const LABELS = { weak: 'Weak', ok: 'OK', strong: 'Strong' };

describe('PasswordStrength', () => {
  it('draws no track before the field has been typed in', () => {
    // An empty grey meter reads as a verdict on a password nobody has entered.
    const { container } = render(
      <PasswordStrength password="" labels={LABELS} hint="At least 8 characters" />,
    );
    expect(container.querySelector('.bg-secondary')).toBeNull();
  });

  it('keeps the hint visible while the track is hidden', () => {
    const { getByText } = render(
      <PasswordStrength password="" labels={LABELS} hint="At least 8 characters" />,
    );
    expect(getByText('At least 8 characters')).toBeInTheDocument();
  });

  it('draws the track with the first keystroke', () => {
    const { container, getByText } = render(<PasswordStrength password="abc" labels={LABELS} />);
    expect(container.querySelector('.bg-secondary')).not.toBeNull();
    expect(getByText('Weak')).toBeInTheDocument();
  });
});
