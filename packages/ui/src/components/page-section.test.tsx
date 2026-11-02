import { describe, expect, it } from 'vitest';
import type { MenuItem } from '../types';
import { findSection } from './AppTopbar';

const item = (label: string, url: string): MenuItem => ({ label, url, icon: 'grid' });

const NAV: MenuItem[] = [item('Users', '/users/admin'), item('Files', '/file-storage/')];

describe('findSection', () => {
  it('resolves a declared section url to its menu entry', () => {
    expect(findSection(NAV, '/users/admin')?.label).toBe('Users');
  });

  it('ignores a trailing-slash mismatch', () => {
    expect(findSection(NAV, '/file-storage')?.label).toBe('Files');
    expect(findSection([item('Files', '/file-storage')], '/file-storage/')?.label).toBe('Files');
  });

  it('returns null when nothing was declared', () => {
    expect(findSection(NAV, null)).toBeNull();
  });

  it('returns null when the section is not in this viewer’s menu', () => {
    // The menu is already permission-filtered, so an unresolvable section means
    // the viewer cannot open it — the crumb must not offer it.
    expect(findSection([item('Files', '/file-storage/')], '/users/admin')).toBeNull();
  });

  it('matches on the exact section, not a parent path', () => {
    // A declared section names one entry; it must not fall through to a
    // shorter entry that merely prefixes it.
    expect(findSection(NAV, '/users')).toBeNull();
  });
});
