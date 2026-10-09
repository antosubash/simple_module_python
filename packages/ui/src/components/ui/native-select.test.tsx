import { render } from '@testing-library/react';
import { NativeSelect, NativeSelectOption } from './native-select';

describe('NativeSelect', () => {
  it('puts wrapperClassName on the wrapper and className on the select (#421)', () => {
    const { container } = render(
      <NativeSelect wrapperClassName="w-full" className="text-xs">
        {/* i18n-exempt: test fixture */}
        <NativeSelectOption value="a">A</NativeSelectOption>
      </NativeSelect>,
    );
    const wrapper = container.querySelector('[data-slot="native-select-wrapper"]');
    const select = container.querySelector('select');
    expect(wrapper?.className).toContain('w-full');
    expect(select?.className).toContain('text-xs');
    expect(select?.className).not.toContain('w-fit');
  });

  it('keeps the wrapper w-fit by default', () => {
    const { container } = render(<NativeSelect />);
    expect(container.querySelector('[data-slot="native-select-wrapper"]')?.className).toContain(
      'w-fit',
    );
  });
});
