import { beforeEach, describe, expect, test } from 'vitest';
import { configureI18n, t, updateI18n } from './index';

describe('configureI18n', () => {
  beforeEach(() => {
    configureI18n({
      locale: 'en',
      messages: {
        'hello': 'Hello',
        'greeting': 'Hello, {name}',
        'items_one': '{count} item',
        'items_other': '{count} items',
      },
    });
  });

  test('returns string for known key', () => {
    expect(t('hello')).toBe('Hello');
  });

  test('interpolates named placeholders', () => {
    expect(t('greeting', { name: 'Ana' })).toBe('Hello, Ana');
  });

  test('picks _one variant for count=1', () => {
    expect(t('items', { count: 1 })).toBe('1 item');
  });

  test('picks _other variant for count>1', () => {
    expect(t('items', { count: 5 })).toBe('5 items');
  });

  test('returns the key when unknown', () => {
    expect(t('missing.key' as unknown as never)).toBe('missing.key');
  });
});

describe('updateI18n', () => {
  test('swaps the active locale', () => {
    configureI18n({ locale: 'en', messages: { hello: 'Hello' } });
    updateI18n({ locale: 'es', messages: { hello: 'Hola' } });
    expect(t('hello')).toBe('Hola');
  });
});
