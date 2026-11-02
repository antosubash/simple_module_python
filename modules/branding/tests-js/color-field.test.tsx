import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, test } from 'vitest';

configureI18n({
  locale: 'en',
  messages: {
    'branding.manage.primary_color_label': 'Primary colour',
    'branding.manage.primary_color_invalid': 'Enter a hex colour',
    'branding.manage.preview_signin_heading': 'Sign in',
    'branding.manage.preview_signin_action': 'Sign in now',
  },
});

import { type PreviewBrand, previewInk } from '../branding/components/BrandingPreview';
import { ColorField } from '../branding/components/ColorField';
import { isValidColor, normalizeHex } from '../branding/components/hex';
import { SignInPreview } from '../branding/components/PreviewSurfaces';

function Harness({ initial }: { initial: string }) {
  const [value, setValue] = useState(initial);
  return <ColorField value={value} fallback="#0f766e" onChange={setValue} />;
}

const BRAND: PreviewBrand = {
  appName: 'Acme',
  accent: '#f5f5f5',
  logoUrl: null,
  logoDarkUrl: null,
  bannerMessage: '',
  footerText: '',
  footerLinks: [],
  menuLabels: [],
};

describe('normalizeHex', () => {
  test('accepts 3/6 digits, optional hash, any case', () => {
    expect(normalizeHex('F5F5F5')).toBe('#f5f5f5');
    expect(normalizeHex('#ABC')).toBe('#aabbcc');
    expect(normalizeHex(' #0f766e ')).toBe('#0f766e');
  });

  test('rejects invalid values', () => {
    for (const bad of ['#zzz', '12345', 'red', '#12345g', '#1234']) {
      expect(normalizeHex(bad)).toBeNull();
      expect(isValidColor(bad)).toBe(false);
    }
    expect(isValidColor('')).toBe(true);
  });
});

describe('ColorField', () => {
  test('flags an invalid value and keeps the swatch valid', () => {
    const { container } = render(<Harness initial="" />);
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '#zzz' } });
    expect(screen.getByRole('alert')).toHaveTextContent('Enter a hex colour');
    expect(container.querySelector('input[type="color"]')).toHaveValue('#0f766e');
  });

  test('normalises a bare hex value on blur', () => {
    render(<Harness initial="" />);
    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'F5F5F5' } });
    expect(screen.queryByRole('alert')).toBeNull();
    fireEvent.blur(input);
    expect(input).toHaveValue('#f5f5f5');
  });
});

describe('preview ink', () => {
  test('light brand colour gets dark ink, dark one gets white', () => {
    expect(previewInk('#f5f5f5')).not.toBe(previewInk('#0f766e'));
    expect(previewInk('#0f766e')).toBe('oklch(1 0 0)');
  });

  test('sign-in button uses the derived ink, not hard-coded white', () => {
    render(<SignInPreview brand={BRAND} />);
    const button = screen.getByText('Sign in now');
    expect(button.className).not.toContain('text-white');
    expect(button.style.color).toBe(previewInk('#f5f5f5'));
  });
});
