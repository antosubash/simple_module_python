import { cn } from '@simple-module-py/ui/lib/utils';

export type StrengthLevel = 'none' | 'weak' | 'ok' | 'strong';

/**
 * How hard the password would be to guess, on a four-step scale.
 *
 * Deliberately coarse and deliberately local: this is feedback while typing,
 * not the policy the server enforces. Length alone earns nothing — sixteen
 * lowercase letters and sixteen digits are both weak — because the thing worth
 * nudging people towards is variety, which is what a guesser has to search.
 */
export function scorePassword(pw: string): { level: StrengthLevel; percent: number } {
  if (pw === '') return { level: 'none', percent: 0 };
  if (pw.length < 8 || /^\d+$/.test(pw)) return { level: 'weak', percent: 33 };

  const classes = [/[a-z]/, /[A-Z]/, /\d/, /[^a-zA-Z0-9]/].filter((re) => re.test(pw)).length;
  if (pw.length >= 12 && classes >= 3) return { level: 'strong', percent: 100 };
  if (/[a-zA-Z]/.test(pw) && /\d/.test(pw)) return { level: 'ok', percent: 66 };
  return { level: 'weak', percent: 33 };
}

interface PasswordStrengthProps {
  password: string;
  labels: Record<Exclude<StrengthLevel, 'none'>, string>;
  /** The rule the password must satisfy, shown alongside the verdict. */
  hint?: string;
  className?: string;
}

const BAR_TONE: Record<Exclude<StrengthLevel, 'none'>, string> = {
  weak: 'bg-red-500',
  ok: 'bg-amber-500',
  strong: 'bg-primary-600',
};

const TEXT_TONE: Record<Exclude<StrengthLevel, 'none'>, string> = {
  weak: 'text-red-700',
  ok: 'text-amber-700',
  strong: 'text-primary-700',
};

export function PasswordStrength({ password, labels, hint, className }: PasswordStrengthProps) {
  const { level, percent } = scorePassword(password);
  return (
    <div className={cn('space-y-1.5', className)}>
      {/* No empty grey track at rest: a meter reading zero says "this password
          is terrible" about a field nobody has typed in yet. It appears with
          the first keystroke, which is also when it starts meaning anything. */}
      {level !== 'none' && (
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
          <div
            className={cn('h-full rounded-full transition-all', BAR_TONE[level])}
            style={{ width: `${percent}%` }}
          />
        </div>
      )}
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        {level !== 'none' && (
          <span className={cn('font-semibold', TEXT_TONE[level])}>{labels[level]}</span>
        )}
        {hint && <span>{hint}</span>}
      </p>
    </div>
  );
}
