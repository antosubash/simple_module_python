import { describe, expect, test } from 'vitest';

import { describeUserAgent } from './user-agent';

const CHROME_MAC =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36';
const SAFARI_MAC =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15';
const EDGE_WIN =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0';
const FIREFOX_LINUX = 'Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0';

describe('describeUserAgent', () => {
  test('names the deck example', () => {
    expect(describeUserAgent(CHROME_MAC)).toEqual({ browser: 'Chrome', os: 'macOS' });
  });

  test('Safari is not mistaken for Chrome', () => {
    expect(describeUserAgent(SAFARI_MAC)).toEqual({ browser: 'Safari', os: 'macOS' });
  });

  test('Edge wins over the Chrome and Safari tokens it also carries', () => {
    // Every Chromium browser impersonates both, so the order of the table is
    // the whole implementation.
    expect(describeUserAgent(EDGE_WIN)).toEqual({ browser: 'Edge', os: 'Windows' });
  });

  test('Firefox on Linux', () => {
    expect(describeUserAgent(FIREFOX_LINUX)).toEqual({ browser: 'Firefox', os: 'Linux' });
  });

  test('an unrecognisable agent is null, not a row of placeholders', () => {
    expect(describeUserAgent('curl/8.6.0')).toBeNull();
    expect(describeUserAgent('')).toBeNull();
    expect(describeUserAgent(undefined)).toBeNull();
  });
});
