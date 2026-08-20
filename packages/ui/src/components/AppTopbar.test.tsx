import { describe, expect, it } from 'vitest';
import type { MenuItem } from '../types';
import { activeSection } from './AppTopbar';

const item = (label: string, url: string): MenuItem => ({ label, url, icon: 'grid' });

const NAV: MenuItem[] = [
  item('Dashboard', '/dashboard/'),
  item('Users', '/users/admin'),
  item('Files', '/file_storage'),
  item('Background tasks', '/admin/background-tasks'),
];

describe('activeSection', () => {
  it('matches a section on its own index', () => {
    expect(activeSection(NAV, '/users/admin')?.label).toBe('Users');
  });

  it('claims sub-pages for their section', () => {
    expect(activeSection(NAV, '/users/admin/add')?.label).toBe('Users');
    expect(activeSection(NAV, '/admin/background-tasks/workers')?.label).toBe('Background tasks');
  });

  it('keeps query strings from breaking the match', () => {
    expect(activeSection(NAV, '/file_storage?q=logo')?.label).toBe('Files');
  });

  it('matches the absolute url Inertia actually reports', () => {
    // page.url arrives as http://host:port/path, not a bare path.
    expect(activeSection(NAV, 'http://localhost:8300/users/admin/add')?.label).toBe('Users');
  });

  it('prefers the longest match when one entry prefixes another', () => {
    // A shorter entry sharing a prefix must not steal the deeper section.
    const nav = [item('Admin', '/admin'), item('Background tasks', '/admin/background-tasks')];
    expect(activeSection(nav, '/admin/background-tasks/workers')?.label).toBe('Background tasks');
  });

  it('returns null for a page outside every section', () => {
    // Permissions pages are sub-pages of another module and register no menu
    // entry — the crumb falls back to the page heading alone rather than
    // inventing a section.
    expect(activeSection(NAV, '/permissions/roles/editor')).toBeNull();
  });

  it('returns null when the user can see no entries at all', () => {
    expect(activeSection([], '/users/admin')).toBeNull();
  });
});
