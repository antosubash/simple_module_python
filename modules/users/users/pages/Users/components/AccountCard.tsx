import { keys, useT } from '@simple-module-py/i18n';
import { ConfirmActionDialog } from '@simple-module-py/ui/components/ConfirmActionDialog';
import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { formatDayMonthYear } from '@simple-module-py/ui/lib/date-format';
import { Copy, KeyRound, UserX } from 'lucide-react';
import type React from 'react';
import { useState } from 'react';

interface Props {
  email: string;
  isExternal: boolean;
  createdAt: string | null;
  disabledAt: string | null;
  isActive: boolean;
  isVerified: boolean;
  savingStatus: boolean;
  savingVerify: boolean;
  onDisable: () => void;
  onEnable: () => void;
  onMarkVerified: () => void;
  onCopyResetLink: () => void;
}

/**
 * "12 Mar 2026" — a date, not a timestamp: the minute an account was created
 * never matters.
 *
 * Day-first, as the deck writes it. The reader's own locale gave "Mar 12,
 * 2026" on a US machine, which is a different order from every other date on
 * the screen.
 */
export function formatDay(value: string | null, fallback: string): string {
  return formatDayMonthYear(value, fallback);
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right">{children}</span>
    </div>
  );
}

/**
 * The facts about this account, and the actions that change them.
 *
 * Previously two cards: "Metadata" listing the facts and "Account status"
 * holding the buttons, which put "Verified: no" in one card and the button
 * that fixes it in another. The status changes stay immediate rather than
 * joining the page's dirty state — locking out a compromised account should
 * not require finding a Save button.
 */
export function AccountCard({
  email,
  isExternal,
  createdAt,
  disabledAt,
  isActive,
  isVerified,
  savingStatus,
  savingVerify,
  onDisable,
  onEnable,
  onMarkVerified,
  onCopyResetLink,
}: Props) {
  const { t } = useT();
  const [confirming, setConfirming] = useState<'disable' | 'reset' | null>(null);
  const emptyValue = t(keys.users.common.empty_value);

  return (
    <Card className="border-border">
      <CardContent className="flex h-full flex-col pt-5">
        <SectionTitle>{t(keys.users.metadata_card.title)}</SectionTitle>
        <div className="space-y-2.5">
          <Row label={t(keys.users.metadata_card.sign_in)}>
            <span className="rounded-full border border-border px-2.5 py-0.5 font-mono text-xs">
              {isExternal
                ? t(keys.users.metadata_card.external_value)
                : t(keys.users.metadata_card.local_badge)}
            </span>
          </Row>
          <Row label={t(keys.users.metadata_card.created)}>{formatDay(createdAt, emptyValue)}</Row>
          <Row label={t(keys.users.metadata_card.verified)}>
            {isVerified ? (
              <span className="text-primary-700 dark:text-primary-400">
                {t(keys.users.metadata_card.yes)}
              </span>
            ) : (
              <span className="inline-flex items-center gap-2">
                <span className="text-amber-700 dark:text-amber-400">
                  {t(keys.users.metadata_card.no)}
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={onMarkVerified}
                  disabled={savingVerify}
                  className="max-lg:min-h-11"
                >
                  {savingVerify
                    ? t(keys.users.common.saving)
                    : t(keys.users.metadata_card.mark_verified)}
                </Button>
              </span>
            )}
          </Row>
          <Row label={t(keys.users.metadata_card.disabled_at)}>
            {formatDay(disabledAt, emptyValue)}
          </Row>
        </div>

        <div className="mt-auto flex flex-wrap gap-2 pt-5">
          {isActive ? (
            <Button
              variant="outline"
              className="max-lg:min-h-11"
              disabled={savingStatus}
              onClick={() => setConfirming('disable')}
            >
              {savingStatus
                ? t(keys.users.common.saving)
                : t(keys.users.account_status.disable_button)}
            </Button>
          ) : (
            <Button className="max-lg:min-h-11" onClick={onEnable} disabled={savingStatus}>
              {savingStatus
                ? t(keys.users.common.saving)
                : t(keys.users.account_status.enable_button)}
            </Button>
          )}
          {!isExternal && (
            <Button
              variant="outline"
              className="gap-1.5 text-muted-foreground max-lg:min-h-11"
              onClick={() => setConfirming('reset')}
            >
              <Copy className="size-3.5" aria-hidden="true" />
              {t(keys.users.account_status.copy_reset_link)}
            </Button>
          )}
        </div>
        {isExternal && (
          <p className="mt-3 text-sm text-muted-foreground">
            {t(keys.users.account_status.external_note)}
          </p>
        )}
      </CardContent>

      <ConfirmActionDialog
        open={confirming === 'disable'}
        onOpenChange={(open) => !open && setConfirming(null)}
        icon={UserX}
        title={t(keys.users.account_status.disable_confirm_title, { email })}
        description={t(keys.users.account_status.disable_confirm_body)}
        confirmLabel={t(keys.users.account_status.disable_action)}
        cancelLabel={t(keys.users.common.cancel)}
        onConfirm={onDisable}
      />
      <ConfirmActionDialog
        open={confirming === 'reset'}
        onOpenChange={(open) => !open && setConfirming(null)}
        tone="primary"
        icon={KeyRound}
        title={t(keys.users.account_status.reset_confirm_title, { email })}
        description={t(keys.users.account_status.reset_confirm_body)}
        confirmLabel={t(keys.users.account_status.reset_action)}
        cancelLabel={t(keys.users.common.cancel)}
        onConfirm={onCopyResetLink}
      />
    </Card>
  );
}
