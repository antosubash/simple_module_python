/**
 * Which browser and OS the reader is using, from the UA string.
 *
 * Only ever used to *describe the current browser to its own user* — the
 * Sessions card's "This browser · Chrome on macOS". It is not an
 * authentication or feature-detection input, and it does not have to be right
 * about anything the reader cannot see for themselves, which is why a short
 * ordered table beats a UA-parsing dependency here.
 *
 * Order matters: every Chromium browser claims to be Safari and most claim to
 * be Chrome, so the more specific brand has to be tested first.
 */

const BROWSERS: [RegExp, string][] = [
  [/\bEdg[A-Z]?\//, 'Edge'],
  [/\bOPR\/|\bOpera\//, 'Opera'],
  [/\bSamsungBrowser\//, 'Samsung Internet'],
  [/\bFirefox\/|\bFxiOS\//, 'Firefox'],
  // No word boundary before `Chrome`: a headless build reports
  // `HeadlessChrome/...`, which is still Chrome and was falling through to
  // the Safari token every Chromium UA also carries.
  [/Chrome\/|CriOS\//, 'Chrome'],
  [/\bSafari\//, 'Safari'],
];

const SYSTEMS: [RegExp, string][] = [
  [/\bWindows\b/, 'Windows'],
  [/\bAndroid\b/, 'Android'],
  [/\b(iPhone|iPad|iPod)\b/, 'iOS'],
  [/\bMac OS X\b|\bMacintosh\b/, 'macOS'],
  [/\bCrOS\b/, 'ChromeOS'],
  [/\bLinux\b/, 'Linux'],
];

function firstMatch(table: [RegExp, string][], ua: string): string | null {
  for (const [pattern, name] of table) {
    if (pattern.test(ua)) return name;
  }
  return null;
}

export interface BrowserDescription {
  browser: string;
  os: string;
}

/**
 * `{ browser: 'Chrome', os: 'macOS' }`, or null when neither can be named.
 *
 * Null rather than "Unknown on Unknown": the caller drops the segment
 * entirely, which is honest, where a row of placeholders reads like a bug.
 */
export function describeUserAgent(ua: string | undefined | null): BrowserDescription | null {
  if (!ua) return null;
  const browser = firstMatch(BROWSERS, ua);
  const os = firstMatch(SYSTEMS, ua);
  if (!browser || !os) return null;
  return { browser, os };
}
