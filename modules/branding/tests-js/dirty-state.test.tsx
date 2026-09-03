import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

configureI18n({
  locale: 'en',
  messages: {
    'branding.manage.preset_label': 'Presets',
  },
});

import { type BrandingForm, countBrandingChanges } from '../branding/components/dirty';
import { PresetField } from '../branding/components/PresetField';

const BASELINE: BrandingForm = {
  appName: 'Acme Admin',
  color: '#0f766e',
  designPack: '',
  bannerMessage: '',
  bannerSeverity: 'info',
  footerLinks: [{ label: 'Privacy', href: '/privacy' }],
};

describe('countBrandingChanges', () => {
  test('an untouched form is not dirty', () => {
    expect(countBrandingChanges({ ...BASELINE }, BASELINE)).toBe(0);
  });

  test('counts each changed field once', () => {
    const form: BrandingForm = {
      ...BASELINE,
      appName: 'Acme',
      color: '#4f46e5',
      bannerMessage: 'Maintenance window',
      footerLinks: [],
    };

    expect(countBrandingChanges(form, BASELINE)).toBe(4);
  });

  test('the whole footer list is one change however many rows move', () => {
    const form: BrandingForm = {
      ...BASELINE,
      footerLinks: [
        { label: 'Privacy', href: '/privacy' },
        { label: 'Status', href: 'https://status.acme.co' },
        { label: 'Terms', href: '/terms' },
      ],
    };

    expect(countBrandingChanges(form, BASELINE)).toBe(1);
  });

  test('reordering the same links still counts as a change', () => {
    const baseline: BrandingForm = {
      ...BASELINE,
      footerLinks: [
        { label: 'Privacy', href: '/privacy' },
        { label: 'Status', href: '/status' },
      ],
    };
    const form: BrandingForm = {
      ...baseline,
      footerLinks: [...baseline.footerLinks].reverse(),
    };

    expect(countBrandingChanges(form, baseline)).toBe(1);
  });

  test('a severity change with no banner text is not a pending change', () => {
    // Severity only colours a banner that exists; counting it would make the
    // header claim unsaved work for a setting nothing renders.
    const form: BrandingForm = { ...BASELINE, bannerSeverity: 'danger' };

    expect(countBrandingChanges(form, BASELINE)).toBe(0);
  });

  test('a severity change alongside a banner does count', () => {
    const baseline: BrandingForm = { ...BASELINE, bannerMessage: 'Heads up' };
    const form: BrandingForm = { ...baseline, bannerSeverity: 'danger' };

    expect(countBrandingChanges(form, baseline)).toBe(1);
  });
});

describe('PresetField', () => {
  const OPTIONS = [
    { key: 'emerald', label: 'emerald', swatch: '#0f766e' },
    { key: 'slate', label: 'slate', swatch: '#475569' },
  ];

  test('marks the preset matching the current colour', () => {
    render(
      <PresetField options={OPTIONS} activeColor="#0F766E" onSelect={vi.fn()} disabled={false} />,
    );

    expect(screen.getByRole('button', { name: 'emerald' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'slate' })).toHaveAttribute('aria-pressed', 'false');
  });

  test('choosing a preset stages its colour instead of posting', () => {
    const onSelect = vi.fn();
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    render(
      <PresetField options={OPTIONS} activeColor="#0f766e" onSelect={onSelect} disabled={false} />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'slate' }));

    expect(onSelect).toHaveBeenCalledWith('#475569');
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
