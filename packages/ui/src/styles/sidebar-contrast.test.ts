// Normal-size sidebar labels must meet WCAG AA, including account-row hover (#670).
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { compile } from '@tailwindcss/node';
import postcss from 'postcss';
import { describe, expect, it } from 'vitest';

const ROOT = resolve(__dirname, '../../../..');

/** OKLCH → OKLab → linear sRGB → WCAG relative luminance. */
function luminance(lightness: number, chroma: number, hue: number, opacity = 1): number {
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
  const channels = rgb.map((linear) => {
    const clipped = Math.max(0, Math.min(1, linear));
    const encoded = clipped <= 0.0031308 ? 12.92 * clipped : 1.055 * clipped ** (1 / 2.4) - 0.055;
    const mixed = encoded * opacity + 1 - opacity;
    return mixed <= 0.04045 ? mixed / 12.92 : ((mixed + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
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

it('keeps dark muted text at AA contrast on the page, cards and muted surfaces (#1160)', async () => {
  const base = join(ROOT, 'packages/ui/src/styles');
  const compiler = await compile(readFileSync(join(base, 'globals.css'), 'utf8'), {
    base,
    onDependency() {},
  });
  const tokens = new Map<string, number>();
  postcss.parse(compiler.build(['text-muted-foreground'])).walkRules((rule) => {
    if (rule.selector !== '.dark') return;
    rule.walkDecls((decl) => {
      if (!['--muted-foreground', '--background', '--card', '--muted'].includes(decl.prop)) return;
      const color = decl.value.match(/^oklch\(([\d.]+) ([\d.]+) ([\d.]+)\)$/);
      if (color) tokens.set(decl.prop, luminance(+color[1], +color[2], +color[3]));
    });
  });
  const fg = tokens.get('--muted-foreground');
  expect(fg).toBeDefined();
  for (const surface of ['--background', '--card', '--muted']) {
    const bg = tokens.get(surface);
    expect(bg).toBeDefined();
    expect(ratio(fg as number, bg as number), surface).toBeGreaterThanOrEqual(4.5);
  }
});

// Read the compiled theme, so these checks cover the values Tailwind emits.
async function themeTokens(selector: string) {
  const base = join(ROOT, 'packages/ui/src/styles');
  const compiler = await compile(readFileSync(join(base, 'globals.css'), 'utf8'), {
    base,
    onDependency() {},
  });
  const tokens = new Map<string, number>();
  postcss
    .parse(compiler.build(['bg-primary', 'text-primary-text', 'text-primary-text-hover']))
    .walkRules((rule) => {
      if (
        !rule.selector
          .split(',')
          .map((s) => s.trim())
          .some((s) => s === ':root' || s === selector)
      )
        return;
      rule.walkDecls((decl) => {
        const color = decl.value.match(/^oklch\(([\d.]+) ([\d.]+) ([\d.]+)\)$/);
        if (color) tokens.set(decl.prop, luminance(+color[1], +color[2], +color[3]));
      });
    });
  return tokens;
}

it('keeps light primary buttons and active sidebar text at AA, including button hover (#1184)', async () => {
  const tokens = await themeTokens(':root');
  const fg = tokens.get('--primary-foreground') as number;
  const bg = tokens.get('--primary') as number;
  expect(fg).toBeDefined();
  expect(bg).toBeDefined();
  expect(ratio(fg, bg)).toBeGreaterThanOrEqual(4.5);
  // Button hover is bg-primary/90, composited over a white card.
  const color = readFileSync(join(ROOT, 'packages/ui/src/styles/theme.css'), 'utf8').match(
    /--primary: oklch\(([\d.]+) ([\d.]+) ([\d.]+)\)/,
  );
  expect(color).not.toBeNull();
  if (color)
    expect(ratio(fg, luminance(+color[1], +color[2], +color[3], 0.9))).toBeGreaterThanOrEqual(4.5);
  expect(
    ratio(
      tokens.get('--sidebar-primary-foreground') as number,
      tokens.get('--sidebar-primary') as number,
    ),
  ).toBeGreaterThanOrEqual(4.5);
});

it('keeps dark primary text at AA on settings surfaces, including selected rows (#1184)', async () => {
  const tokens = await themeTokens('.dark');
  const fg = tokens.get('--color-primary-text') as number;
  expect(fg).toBeDefined();
  for (const name of ['--background', '--card', '--muted']) {
    const bg = tokens.get(name) as number;
    expect(bg).toBeDefined();
    expect(ratio(fg, bg), name).toBeGreaterThanOrEqual(4.5);
    expect(
      ratio(tokens.get('--color-primary-text-hover') as number, bg),
      name,
    ).toBeGreaterThanOrEqual(4.5);
    expect(ratio(fg, bg * 0.9 + luminance(0.59, 0.14, 158) * 0.1), name).toBeGreaterThanOrEqual(
      4.5,
    );
  }
});
