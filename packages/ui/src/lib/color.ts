/**
 * Colour helpers for runtime brand theming.
 *
 * A deployment configures a single brand colour (`#rrggbb`). The app's Tailwind
 * theme, however, is a 10-step ramp (`--color-primary-50 … -900`) plus the base
 * `--primary` token. To make the *whole* brand surface follow the configured
 * colour — buttons (`bg-primary`) **and** the logo-badge gradient
 * (`from-primary-600 to-primary-800`) and the auth mesh blobs — we derive the
 * full ramp from that one hex at runtime.
 *
 * Strategy: keep the designed *lightness* ladder exactly (so contrast stays as
 * the designer intended), replace the *hue* with the brand colour's hue, and
 * scale the *chroma* by how saturated the brand colour is relative to the
 * default. A near-grey brand yields a near-grey ramp; a vivid brand yields a
 * vivid ramp — both with the original light/dark contrast.
 */

export interface Oklch {
  l: number;
  c: number;
  h: number;
}

/**
 * The default theme's primary ramp, mirrored from
 * `packages/ui/src/styles/globals.css` (`--color-primary-*`). Only lightness and
 * chroma are used; the hue is replaced per brand colour. Keep in sync with the
 * stylesheet — a unit test pins the step list.
 */
export const BASE_PRIMARY_RAMP: { step: number; l: number; c: number }[] = [
  { step: 50, l: 0.97, c: 0.02 },
  { step: 100, l: 0.93, c: 0.05 },
  { step: 200, l: 0.86, c: 0.09 },
  { step: 300, l: 0.79, c: 0.13 },
  { step: 400, l: 0.71, c: 0.16 },
  { step: 500, l: 0.66, c: 0.16 },
  { step: 600, l: 0.59, c: 0.14 },
  { step: 700, l: 0.5, c: 0.11 },
  { step: 800, l: 0.42, c: 0.09 },
  { step: 900, l: 0.35, c: 0.07 },
];

/** Chroma of the default ramp's 600 step — the reference for chroma scaling. */
const BASE_REFERENCE_CHROMA = BASE_PRIMARY_RAMP.find((s) => s.step === 600)?.c ?? 0.14;
/** Clamp the chroma scale so a vivid pick can't blow far out of gamut. */
const MAX_CHROMA_SCALE = 1.8;

function srgbToLinear(channel: number): number {
  return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
}

/** Parse `#rgb` / `#rrggbb` into linear-light RGB in `[0, 1]`, or null. */
function parseHex(hex: string): [number, number, number] | null {
  const m = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return null;
  let h = m[1];
  if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
  const r = Number.parseInt(h.slice(0, 2), 16) / 255;
  const g = Number.parseInt(h.slice(2, 4), 16) / 255;
  const b = Number.parseInt(h.slice(4, 6), 16) / 255;
  return [srgbToLinear(r), srgbToLinear(g), srgbToLinear(b)];
}

/** Convert an `#rrggbb` colour to OKLCH, or null when it can't be parsed. */
export function hexToOklch(hex: string): Oklch | null {
  const lin = parseHex(hex);
  if (!lin) return null;
  const [r, g, b] = lin;

  // Linear sRGB → OKLab (Björn Ottosson's matrices).
  const l_ = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m_ = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s_ = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);

  const L = 0.2104542553 * l_ + 0.793617785 * m_ - 0.0040720468 * s_;
  const a = 1.9779984951 * l_ - 2.428592205 * m_ + 0.4505937099 * s_;
  const bb = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.808675766 * s_;

  const c = Math.hypot(a, bb);
  let h = (Math.atan2(bb, a) * 180) / Math.PI;
  if (h < 0) h += 360;
  return { l: L, c, h };
}

function round(n: number, places: number): number {
  const f = 10 ** places;
  return Math.round(n * f) / f;
}

function oklchString({ l, c, h }: Oklch): string {
  return `oklch(${round(l, 4)} ${round(c, 4)} ${round(h, 2)})`;
}

/**
 * Derive the CSS custom properties that re-theme the primary ramp to `hex`.
 *
 * Returns a map of `--color-primary-<step>` → `oklch(…)` (plus the base
 * `--primary` / `--sidebar-primary` set to the brand colour itself). Returns
 * null for an unparseable colour so callers can leave the default theme intact.
 */
export function deriveBrandRamp(hex: string): Record<string, string> | null {
  const brand = hexToOklch(hex);
  if (!brand) return null;

  const chromaScale = Math.min(brand.c / BASE_REFERENCE_CHROMA, MAX_CHROMA_SCALE);
  const vars: Record<string, string> = {};
  for (const { step, l, c } of BASE_PRIMARY_RAMP) {
    vars[`--color-primary-${step}`] = oklchString({ l, c: c * chromaScale, h: brand.h });
  }
  // Keep the base tokens as the exact picked colour: `bg-primary` should be
  // precisely what the admin chose, while the ramp drives gradients/tints.
  vars['--primary'] = hex;
  vars['--sidebar-primary'] = hex;
  return vars;
}
