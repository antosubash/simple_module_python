/**
 * Shared semantic-tone → Tailwind class lookup. Use whenever you'd otherwise
 * hand-roll `border-primary-200 bg-primary-50 text-primary-700` style triplets
 * for status badges, stat-card deltas, or row chrome.
 */
export const TONE = {
  success: 'border-primary-200 bg-primary-50 text-primary-700',
  info: 'border-blue-200 bg-blue-50 text-blue-700',
  warning: 'border-amber-200 bg-amber-50 text-amber-700',
  destructive: 'border-red-200 bg-red-50 text-red-700',
  default: 'border-border bg-secondary text-muted-foreground',
} as const;

export type Tone = keyof typeof TONE;
