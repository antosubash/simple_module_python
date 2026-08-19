import { describe, expect, it } from 'vitest';
import { isUnder, toPath } from './current-path';

describe('toPath', () => {
  it('reduces an absolute page url to its path', () => {
    expect(toPath('http://localhost:8300/users/admin/add')).toBe('/users/admin/add');
  });

  it('leaves a root-relative path alone', () => {
    expect(toPath('/users/admin')).toBe('/users/admin');
  });

  it('drops query and hash', () => {
    expect(toPath('http://x/files?q=logo#top')).toBe('/files');
    expect(toPath('/audit_log?correlation_id=abc')).toBe('/audit_log');
  });
});

describe('isUnder', () => {
  it('matches a section on its own url', () => {
    expect(isUnder('/users/admin', '/users/admin')).toBe(true);
  });

  it('matches an absolute url against a path section — the case that was broken', () => {
    expect(isUnder('http://localhost:8300/users/admin', '/users/admin')).toBe(true);
    expect(isUnder('http://localhost:8300/users/admin/add', '/users/admin')).toBe(true);
  });

  it('ignores trailing slashes on either side', () => {
    expect(isUnder('http://x/dashboard/', '/dashboard/')).toBe(true);
    expect(isUnder('/dashboard', '/dashboard/')).toBe(true);
    expect(isUnder('/audit_log/', '/audit_log/')).toBe(true);
  });

  it('does not let a section claim a sibling that merely shares its prefix', () => {
    expect(isUnder('/users-archive', '/users')).toBe(false);
    expect(isUnder('/settings-legacy/x', '/settings')).toBe(false);
  });

  it('claims genuine sub-paths', () => {
    expect(isUnder('/admin/background-tasks/workers', '/admin/background-tasks/')).toBe(true);
  });

  it('is false for an unrelated page', () => {
    expect(isUnder('/branding/', '/users/admin')).toBe(false);
  });
});
