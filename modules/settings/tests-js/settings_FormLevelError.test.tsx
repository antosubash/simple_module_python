import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import { FormLevelError } from '../settings/pages/components/FormLevelError';

describe('FormLevelError', () => {
  test('renders a model-level error flashed under errors.general', () => {
    render(<FormLevelError errors={{ general: 'tenant/user scope requires a scope_id' }} />);
    expect(screen.getByRole('alert')).toHaveTextContent('tenant/user scope requires a scope_id');
  });

  test('renders nothing for field-only errors', () => {
    const { container } = render(<FormLevelError errors={{ key: 'required' }} />);
    expect(container).toBeEmptyDOMElement();
  });
});
