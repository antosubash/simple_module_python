import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';

import { InterpolatedText } from './InterpolatedText';

/** Stands in for `t(key, params)` over a catalog entry. */
const translate = (template: string) => (slot: string) => template.replace('{value}', slot);

describe('InterpolatedText', () => {
  test('renders the value where the placeholder sits', () => {
    const { container } = render(
      <InterpolatedText render={translate('Your role does not include {value}. Ask an admin.')}>
        <code>settings.manage</code>
      </InterpolatedText>,
    );
    expect(container.textContent).toBe('Your role does not include settings.manage. Ask an admin.');
    expect(screen.getByText('settings.manage').tagName).toBe('CODE');
  });

  test('the placeholder may lead the sentence', () => {
    // The whole point of one key with one placeholder: a translation is free
    // to put the value first, which splicing a prefix and a suffix cannot do.
    const { container } = render(
      <InterpolatedText render={translate('{value} of 42 granted')}>
        <b>7</b>
      </InterpolatedText>,
    );
    expect(container.textContent).toBe('7 of 42 granted');
  });

  test('a translation that dropped the placeholder still shows the value', () => {
    const { container } = render(
      <InterpolatedText render={() => 'Permiso insuficiente.'}>
        <code>settings.manage</code>
      </InterpolatedText>,
    );
    expect(container.textContent).toBe('Permiso insuficiente. settings.manage');
  });

  test('a repeated placeholder keeps every word of the copy', () => {
    // Rendering the value twice would be worse than rendering it once, but
    // dropping the tail would delete real translated text.
    const { container } = render(
      <InterpolatedText render={(slot) => `A${slot}B${slot}C`}>
        <b>x</b>
      </InterpolatedText>,
    );
    expect(container.textContent).toBe('AxBC');
  });

  test('no sentinel character survives into the DOM', () => {
    const { container } = render(
      <InterpolatedText render={translate('before {value} after')}>
        <b>x</b>
      </InterpolatedText>,
    );
    expect(container.textContent).not.toContain('\u0000');
  });
});
