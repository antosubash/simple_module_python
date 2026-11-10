import { describe, expect, it } from 'vitest';
import { splitValidationErrors } from '../settings/ui/components/validation-errors';

describe('splitValidationErrors', () => {
  it('maps located errors to their field', () => {
    const r = splitValidationErrors([{ loc: ['a'], msg: 'Value error, too big' }]);
    expect(r.fields).toEqual({ a: 'too big' });
    expect(r.form).toEqual([]);
  });

  it('keeps model-level (empty loc) errors as form errors', () => {
    const r = splitValidationErrors([{ loc: [], msg: 'Value error, timeout exceeds lease' }]);
    expect(r.fields).toEqual({});
    expect(r.form).toEqual(['timeout exceeds lease']);
  });

  it('surfaces a string detail at form level, so a 422 is never swallowed', () => {
    expect(splitValidationErrors('nope')).toEqual({ fields: {}, form: ['nope'] });
  });

  it('tolerates a detail that is neither a list nor a string', () => {
    expect(splitValidationErrors(null)).toEqual({ fields: {}, form: [] });
    expect(splitValidationErrors({ msg: 'x' })).toEqual({ fields: {}, form: [] });
  });

  it('maps a nested loc to its field with the path in the message', () => {
    const r = splitValidationErrors([{ loc: ['body', 'types', 0], msg: 'bad item' }], ['types']);
    expect(r.fields).toEqual({ types: '0: bad item' });
    expect(r.form).toEqual([]);
  });

  it('puts a loc naming no field at form level', () => {
    const r = splitValidationErrors([{ loc: ['value'], msg: 'too long' }], ['types']);
    expect(r.fields).toEqual({});
    expect(r.form).toEqual(['value: too long']);
  });
});
