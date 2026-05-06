import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import {
  Box,
  ChevronRight,
  FileText,
  type LucideIcon,
  Mail,
  ShoppingCart,
  Users,
} from 'lucide-react';
import { TONE } from './doctor-data';

type Tone = keyof typeof TONE;

const ATTENTION: { icon: LucideIcon; label: string }[] = [
  { icon: Mail, label: '1 invite expiring tomorrow' },
  { icon: ShoppingCart, label: '3 orders awaiting fulfillment' },
  { icon: FileText, label: '2 posts pending review' },
];

const TEAM = [
  { initial: 'A', name: 'Admin', role: 'Owner', ago: 'now' },
  { initial: 'J', name: 'Jane Doe', role: 'Admin', ago: '4m' },
  { initial: 'P', name: 'Pat Morgan', role: 'Editor', ago: '12m' },
];

const ACTIVITY: { icon: LucideIcon; who: string; did: string; when: string; tone: Tone }[] = [
  {
    icon: Users,
    who: 'admin',
    did: 'invited liu@acme.dev as editor',
    when: '2 min ago',
    tone: 'success',
  },
  {
    icon: ShoppingCart,
    who: 'jane',
    did: 'fulfilled order #1042',
    when: '14 min ago',
    tone: 'info',
  },
  {
    icon: FileText,
    who: 'pat',
    did: "published post 'Q4 wrap-up'",
    when: '1h ago',
    tone: 'success',
  },
  {
    icon: Box,
    who: 'anto',
    did: 'updated product Widget A pricing',
    when: '3h ago',
    tone: 'default',
  },
];

export function DemoPlaceholders({ totalUsers }: { totalUsers: number }) {
  return (
    <>
      <Card className="border-border">
        <CardContent className="pt-5">
          <SectionTitle>Recent activity (demo)</SectionTitle>
          <div className="-mx-1">
            {ACTIVITY.map((row) => (
              <div
                key={`${row.who}-${row.when}`}
                className="flex items-center gap-3 border-t border-border px-1 py-3 first:border-t-0"
              >
                <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-secondary text-muted-foreground">
                  <row.icon className="h-4 w-4" aria-hidden="true" />
                </span>
                <div className="flex-1 text-sm">
                  <div className="text-foreground">
                    <strong className="font-semibold">{row.who}</strong>{' '}
                    <span className="text-muted-foreground">{row.did}</span>
                  </div>
                  <div className="mt-0.5 text-xs text-muted-foreground">{row.when}</div>
                </div>
                <Badge variant="outline" className={`text-[11px] ${TONE[row.tone]}`}>
                  {row.tone}
                </Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-col gap-4">
        <Card className="border-border">
          <CardContent className="pt-5">
            <SectionTitle>Needs your attention (demo)</SectionTitle>
            <div className="flex flex-col gap-2">
              {ATTENTION.map((row) => (
                <div
                  key={row.label}
                  className="flex items-center gap-2.5 rounded-lg border border-border px-3 py-2.5"
                >
                  <row.icon className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                  <span className="flex-1 text-sm text-foreground">{row.label}</span>
                  <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card className="border-border">
          <CardContent className="pt-5">
            <SectionTitle
              right={
                <span className="font-mono text-[11px] text-muted-foreground">
                  {TEAM.length} of {totalUsers || TEAM.length}
                </span>
              }
            >
              Team online (demo)
            </SectionTitle>
            <div className="flex flex-col gap-2.5">
              {TEAM.map((u) => (
                <div key={u.name} className="flex items-center gap-2.5">
                  <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-primary-600 to-primary-800 text-xs font-bold text-white font-[var(--font-display)]">
                    {u.initial}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-[13px] font-semibold text-foreground truncate">
                      {u.name}
                    </div>
                    <div className="text-[11px] text-muted-foreground">{u.role}</div>
                  </div>
                  <span className="font-mono text-[11px] text-muted-foreground">{u.ago}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
