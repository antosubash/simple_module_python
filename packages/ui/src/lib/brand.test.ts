import { describe, expect, it } from 'vitest';
import { darkSurfaceLogo } from './brand';

describe('darkSurfaceLogo', () => {
  it('prefers the dark variant when one is uploaded', () => {
    expect(darkSurfaceLogo({ logoUrl: '/logo', logoDarkUrl: '/logo-dark' })).toBe('/logo-dark');
  });

  it('falls back to the primary logo so single-logo sites are unchanged', () => {
    expect(darkSurfaceLogo({ logoUrl: '/logo', logoDarkUrl: null })).toBe('/logo');
  });

  it('returns null when neither is set, so the initial badge renders', () => {
    expect(darkSurfaceLogo({ logoUrl: null, logoDarkUrl: null })).toBeNull();
  });

  it('tolerates a missing branding prop (the module is optional)', () => {
    expect(darkSurfaceLogo(null)).toBeNull();
    expect(darkSurfaceLogo(undefined)).toBeNull();
  });
});
