import { describe, expect, it } from 'vitest';
import {
  livePasswordIssue,
  mapRegisterError,
  meetsPasswordPolicy,
  passwordPolicyIssue,
} from '../users/auth_local/registerErrors';

describe('mapRegisterError', () => {
  it('maps an existing account onto the email field', () => {
    expect(mapRegisterError({ detail: 'REGISTER_USER_ALREADY_EXISTS' })).toEqual({
      field: 'email',
      code: 'exists',
    });
  });

  it('maps each server password reason onto a code, never the raw string', () => {
    const reason = (r: string) =>
      mapRegisterError({ detail: { code: 'REGISTER_INVALID_PASSWORD', reason: r } });
    expect(reason('Password must be at least 8 characters, not counting spaces').code).toBe(
      'password_length',
    );
    expect(reason('Password cannot contain your email').code).toBe('password_contains_email');
    expect(reason('Password cannot be all numbers').code).toBe('password_numeric');
    expect(reason('something new').code).toBe('password_invalid');
    expect(reason('x').field).toBe('password');
  });

  it('maps a pydantic 422 by the field in loc', () => {
    expect(
      mapRegisterError({ detail: [{ loc: ['body', 'email'], msg: 'bad', type: 'value_error' }] }),
    ).toEqual({ field: 'email', code: 'email_invalid' });
    expect(mapRegisterError({ detail: [{ loc: ['body', 'password'], msg: 'x' }] }).field).toBe(
      'password',
    );
  });

  it('falls back to a generic form error', () => {
    expect(mapRegisterError({})).toEqual({ field: 'form', code: 'failed' });
    expect(mapRegisterError({ detail: 'WHATEVER' }).code).toBe('failed');
    expect(mapRegisterError(null).code).toBe('failed');
  });
});

describe('meetsPasswordPolicy', () => {
  it('matches the server policy', () => {
    expect(meetsPasswordPolicy('short1', 'a@b.co')).toBe(false);
    expect(meetsPasswordPolicy('        ', 'a@b.co')).toBe(false);
    expect(meetsPasswordPolicy('12345678', 'a@b.co')).toBe(false);
    expect(meetsPasswordPolicy('a@b.co', 'a@b.co')).toBe(false);
    expect(meetsPasswordPolicy('longenough', 'a@b.co')).toBe(true);
  });
});

describe('passwordPolicyIssue', () => {
  it('names the rule the server would reject on', () => {
    expect(passwordPolicyIssue('short1', 'a@b.co')).toBe('password_length');
    expect(passwordPolicyIssue('        ', 'a@b.co')).toBe('password_length');
    expect(passwordPolicyIssue('qa@example.com', 'qa@example.com')).toBe('password_contains_email');
    expect(passwordPolicyIssue('12345678', 'a@b.co')).toBe('password_numeric');
    expect(passwordPolicyIssue('longenough', 'a@b.co')).toBeNull();
  });
});

describe('livePasswordIssue', () => {
  it('stays quiet until the password reaches the minimum length', () => {
    expect(livePasswordIssue('1234', 'a@b.co')).toBeNull();
    expect(livePasswordIssue('        ', 'a@b.co')).toBe('password_length');
    expect(livePasswordIssue('example.com', 'qa@example.com')).toBe('password_contains_email');
    expect(livePasswordIssue('12345678', 'a@b.co')).toBe('password_numeric');
  });
});
