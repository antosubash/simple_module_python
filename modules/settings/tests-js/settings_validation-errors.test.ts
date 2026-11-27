import { configureI18n } from '@simple-module-py/i18n';
import { beforeEach, describe, expect, it } from 'vitest';
import de from '../settings/locales/de.json';
import en from '../settings/locales/en.json';
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

function flatten(catalog: object, prefix = 'settings'): Record<string, string> {
  return Object.fromEntries(
    Object.entries(catalog).flatMap(([key, value]) =>
      typeof value === 'string'
        ? [[`${prefix}.${key}`, value]]
        : Object.entries(flatten(value, `${prefix}.${key}`)),
    ),
  );
}

describe.each([
  ['en', en],
  ['de', de],
] as const)('validation messages in %s', (locale, catalog) => {
  beforeEach(() => configureI18n({ locale, messages: flatten(catalog) }));

  it.each([
    ['greater_than', { gt: 0 }, 'Must be greater than 0.', 'Muss größer als 0 sein.'],
    ['greater_than_equal', { ge: 1 }, 'Must be at least 1.', 'Muss mindestens 1 sein.'],
    ['less_than', { lt: 2.5 }, 'Must be less than 2.5.', 'Muss kleiner als 2.5 sein.'],
    ['less_than_equal', { le: 0 }, 'Must be at most 0.', 'Darf höchstens 0 sein.'],
    ['int_parsing', {}, 'Enter a whole number.', 'Geben Sie eine ganze Zahl ein.'],
    ['int_from_float', {}, 'Enter a whole number.', 'Geben Sie eine ganze Zahl ein.'],
    ['float_parsing', {}, 'Enter a number.', 'Geben Sie eine Zahl ein.'],
    ['bool_parsing', {}, 'Enter true or false.', 'Geben Sie true oder false ein.'],
    ['missing', {}, 'This field is required.', 'Dieses Feld ist erforderlich.'],
    [
      'string_too_short',
      { min_length: 2 },
      'Use at least 2 characters.',
      'Verwenden Sie mindestens 2 Zeichen.',
    ],
    [
      'string_too_long',
      { max_length: 10 },
      'Use at most 10 characters.',
      'Verwenden Sie höchstens 10 Zeichen.',
    ],
    ['too_long', { max_length: 3 }, 'Use at most 3 items.', 'Verwenden Sie höchstens 3 Einträge.'],
    [
      'url_parsing',
      { error: 'invalid port number' },
      'Enter a valid URL.',
      'Geben Sie eine gültige URL ein.',
    ],
    [
      'url_scheme',
      { expected_schemes: "'http' or 'https'" },
      "Use a URL with one of these schemes: 'http' or 'https'.",
      "Verwenden Sie eine URL mit einem dieser Schemata: 'http' or 'https'.",
    ],
    [
      'literal_error',
      { expected: "'a' or 'b'" },
      "Choose one of: 'a' or 'b'.",
      "Wählen Sie einen dieser Werte: 'a' or 'b'.",
    ],
    [
      'enum',
      { expected: '1, 2 or 3' },
      'Choose one of: 1, 2 or 3.',
      'Wählen Sie einen dieser Werte: 1, 2 or 3.',
    ],
    [
      'json_invalid',
      { error: 'expected value' },
      'Enter valid JSON.',
      'Geben Sie gültiges JSON ein.',
    ],
  ])('translates %s using its context', (type, ctx, english, german) => {
    const result = splitValidationErrors([
      { loc: ['body', 'setting'], type, ctx, msg: 'Pydantic English message' },
    ]);
    expect(result).toEqual({ fields: { setting: locale === 'en' ? english : german }, form: [] });
  });

  it('translates nested and form errors while preserving paths and multiple messages', () => {
    const result = splitValidationErrors(
      [
        { loc: ['body', 'items', 0], type: 'int_parsing', msg: 'bad integer' },
        { loc: ['items', 1], type: 'int_from_float', msg: 'bad integer' },
        { loc: [], type: 'missing', msg: 'Field required' },
      ],
      ['items'],
    );
    expect(result).toEqual({
      fields: {
        items:
          locale === 'en'
            ? '0: Enter a whole number.; 1: Enter a whole number.'
            : '0: Geben Sie eine ganze Zahl ein.; 1: Geben Sie eine ganze Zahl ein.',
      },
      form: [locale === 'en' ? 'This field is required.' : 'Dieses Feld ist erforderlich.'],
    });
  });

  it.each([
    { type: 'value_error', msg: 'Value error, Choose a reachable host' },
    { type: 'value_error', msg: 'Choose a reachable host' },
    { type: 'future_error', msg: 'Choose a reachable host' },
    { type: 'toString', msg: 'Choose a reachable host' },
    { msg: 'Choose a reachable host' },
  ])('preserves authored or unknown messages: $type', (error) => {
    expect(splitValidationErrors([{ loc: ['host'], ...error }]).fields.host).toBe(
      'Choose a reachable host',
    );
  });

  it('falls back to the server message when interpolation context is missing', () => {
    expect(
      splitValidationErrors([
        { loc: ['size'], type: 'greater_than_equal', msg: 'Input should be at least 1' },
      ]).fields.size,
    ).toBe('Input should be at least 1');
  });
});
