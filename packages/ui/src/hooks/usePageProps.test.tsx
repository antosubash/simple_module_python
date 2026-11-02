import { renderHook } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

const props = {
  auth: { user: null, isAuthenticated: false, permissions: [] },
  menus: { sidebar: [], adminSidebar: [], navbar: [], userDropdown: [] },
  errors: {},
  total: 3,
};

vi.mock('@inertiajs/react', () => ({ usePage: () => ({ props, url: '/x' }) }));

import { usePageProps } from './usePageProps';

describe('usePageProps', () => {
  test('returns page props merged with the shared props', () => {
    const { result } = renderHook(() => usePageProps<{ total: number }>());
    expect(result.current.total).toBe(3);
    expect(result.current.auth.isAuthenticated).toBe(false);
    expect(result.current.errors).toEqual({});
  });
});
