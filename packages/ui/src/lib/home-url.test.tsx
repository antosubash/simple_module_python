import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

let props: Record<string, unknown> = {};
vi.mock('@inertiajs/react', () => ({ usePage: () => ({ props }) }));

import { useHomeUrl } from './home-url';

describe('useHomeUrl', () => {
  beforeEach(() => {
    props = {};
  });

  it('returns the homeUrl shared prop', () => {
    props = { homeUrl: '/home/' };
    expect(renderHook(() => useHomeUrl()).result.current).toBe('/home/');
  });

  it('falls back to / when absent', () => {
    expect(renderHook(() => useHomeUrl()).result.current).toBe('/');
  });
});
