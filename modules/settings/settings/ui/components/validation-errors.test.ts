import { describe, expect, it } from 'vitest';
import { splitValidationErrors } from './validation-errors';

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

  it('tolerates a non-list detail', () => {
    expect(splitValidationErrors('nope')).toEqual({ fields: {}, form: [] });
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
