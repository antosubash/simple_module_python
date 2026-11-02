// Normal-size sidebar labels must meet WCAG AA, including account-row hover (#670).
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const ROOT = resolve(__dirname, '../../../..');

/** OKLCH → OKLab → linear sRGB → WCAG relative luminance. */
function luminance(lightness: number, chroma: number, hue: number): number {
  const a = chroma * Math.cos((hue * Math.PI) / 180);
  const b = chroma * Math.sin((hue * Math.PI) / 180);
  const l = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (lightness - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const rgb = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
  for (const channel of rgb) expect(channel).toBeGreaterThanOrEqual(-1e-6);
  return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
}

function cssFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    if (name === 'node_modules' || name.startsWith('.')) return [];
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return cssFiles(path);
    return name.endsWith('.css') ? [path] : [];
  });
}

/** Every shipped value of each `--color-app-sidebar*` token, as luminance. */
function sidebarTokens(): Map<string, number[]> {
  const tokens = new Map<string, number[]>();
  for (const root of ['packages', 'modules']) {
    for (const path of cssFiles(join(ROOT, root))) {
      const css = readFileSync(path, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
      for (const [, name, value] of css.matchAll(/--color-(app-sidebar[\w-]*):\s*([^;]+);/g)) {
        const match = value.trim().match(/^oklch\(([\d.]+) ([\d.]+) ([\d.]+)\)$/);
        expect(match, `unsupported sidebar colour in ${path}: ${value}`).not.toBeNull();
        if (!match) continue;
        const list = tokens.get(name) ?? [];
        list.push(luminance(Number(match[1]), Number(match[2]), Number(match[3])));
        tokens.set(name, list);
      }
    }
  }
  return tokens;
}

const ratio = (fg: number, bg: number) => (Math.max(fg, bg) + 0.05) / (Math.min(fg, bg) + 0.05);

describe('sidebar text contrast', () => {
  it('converts reference colours correctly', () => {
    expect(luminance(0, 0, 0)).toBeCloseTo(0);
    expect(luminance(1, 0, 0)).toBeCloseTo(1);
    // Neutral OKLab lightness is the cube root of linear luminance.
    expect(luminance(0.5, 0, 0)).toBeCloseTo(0.125);
  });

  it('keeps muted text at 4.5:1 on the sidebar and its hover, and dimmer than normal text', () => {
    const tokens = sidebarTokens();
    const muted = tokens.get('app-sidebar-text-muted') ?? [];
    const normal = tokens.get('app-sidebar-text') ?? [];
    expect(muted.length).toBeGreaterThan(0);
    for (const background of ['app-sidebar', 'app-sidebar-hover']) {
      for (const bg of tokens.get(background) ?? []) {
        for (const fg of muted) {
          expect(ratio(fg, bg)).toBeGreaterThanOrEqual(4.5);
          for (const n of normal) expect(fg).toBeLessThan(n);
        }
      }
    }
  });
});
