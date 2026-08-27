import { keys, useT } from '@simple-module-py/i18n';
import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { TONE } from '@simple-module-py/ui/lib/tone';
import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react';

export interface Diagnostic {
  level: 'error' | 'warning' | 'info';
  code: string;
  message: string;
  module: string;
  file: string | null;
  suggestion: string | null;
}

const LEVEL_VISUALS = {
  error: { Icon: XCircle, color: 'text-red-600', tone: TONE.destructive },
  warning: { Icon: AlertTriangle, color: 'text-amber-600', tone: TONE.warning },
  info: { Icon: Info, color: 'text-muted-foreground', tone: TONE.default },
} as const;

function DiagnosticRow({ d, suggestionLabel }: { d: Diagnostic; suggestionLabel: string }) {
  const { Icon, color, tone } = LEVEL_VISUALS[d.level];
  return (
    <div className="flex items-start gap-3 border-t border-border px-1 py-3 first:border-t-0">
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${color}`} aria-hidden="true" />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold text-foreground">
          <code className="font-mono text-[12px]">{d.code}</code> · {d.module}
        </div>
        <div className="mt-0.5 text-xs text-muted-foreground">{d.message}</div>
        {d.file && (
          <code className="mt-1 inline-block font-mono text-[11px] text-muted-foreground">
            {d.file}
          </code>
        )}
        {d.suggestion && (
          <div className="mt-1 text-[11px] text-muted-foreground">
            {suggestionLabel}: {d.suggestion}
          </div>
        )}
      </div>
      <Badge variant="outline" className={tone}>
        {d.level}
      </Badge>
    </div>
  );
}

export function DiagnosticsCard({ diagnostics }: { diagnostics: Diagnostic[] }) {
  const { t } = useT();
  return (
    <Card className="border-border">
      <CardContent className="pt-5">
        <SectionTitle>{t(keys.dashboard.doctor.diagnostics)}</SectionTitle>
        {diagnostics.length === 0 ? (
          <div className="flex items-center gap-3 rounded-lg border border-border px-4 py-6">
            <CheckCircle2 className="h-5 w-5 text-primary-600" aria-hidden="true" />
            <div>
              <div className="text-sm font-semibold text-foreground">
                {t(keys.dashboard.doctor.all_clear_title)}
              </div>
              <div className="text-xs text-muted-foreground">
                {t(keys.dashboard.doctor.all_clear_hint)}
              </div>
            </div>
          </div>
        ) : (
          <div className="-mx-1">
            {diagnostics.map((d) => (
              <DiagnosticRow
                key={`${d.code}-${d.module}-${d.message}`}
                d={d}
                suggestionLabel={t(keys.dashboard.doctor.suggestion)}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
