import { keys, useT } from '@simple-module-py/i18n';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@simple-module-py/ui/components/ui/select';

/** Mirrors `BANNER_SEVERITIES` in `branding/constants.py`. */
export const BANNER_SEVERITIES = ['info', 'warning', 'danger'] as const;
export type BannerSeverity = (typeof BANNER_SEVERITIES)[number];

/** Matches `MAX_BANNER_MESSAGE_LEN`, so the server never has to reject length. */
export const MAX_BANNER_MESSAGE = 500;

interface BannerFieldProps {
  message: string;
  severity: BannerSeverity;
  onMessageChange: (next: string) => void;
  onSeverityChange: (next: BannerSeverity) => void;
  disabled: boolean;
}

/** Site-wide announcement bar: message + severity. Empty message hides it. */
export function BannerField({
  message,
  severity,
  onMessageChange,
  onSeverityChange,
  disabled,
}: BannerFieldProps) {
  const { t } = useT();
  const severityLabels: Record<BannerSeverity, string> = {
    info: t(keys.branding.manage.banner_severity_info),
    warning: t(keys.branding.manage.banner_severity_warning),
    danger: t(keys.branding.manage.banner_severity_danger),
  };

  return (
    <div className="space-y-2">
      <Label htmlFor="banner_message">{t(keys.branding.manage.banner_label)}</Label>
      <div className="flex flex-wrap items-center gap-3">
        <Input
          id="banner_message"
          value={message}
          maxLength={MAX_BANNER_MESSAGE}
          disabled={disabled}
          placeholder={t(keys.branding.manage.banner_placeholder)}
          onChange={(e) => onMessageChange(e.target.value)}
          className="min-w-60 flex-1"
        />
        <Select
          value={severity}
          disabled={disabled}
          onValueChange={(next) => onSeverityChange(next as BannerSeverity)}
        >
          <SelectTrigger id="banner_severity" className="w-40" aria-label="Banner severity">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {BANNER_SEVERITIES.map((value) => (
              <SelectItem key={value} value={value}>
                {severityLabels[value]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <p className="text-xs text-muted-foreground">{t(keys.branding.manage.banner_help)}</p>
    </div>
  );
}
