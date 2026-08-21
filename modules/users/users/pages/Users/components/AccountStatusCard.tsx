import { keys, useT } from '@simple-module-py/i18n';
import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@simple-module-py/ui/components/ui/alert-dialog';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { Copy } from 'lucide-react';

interface Props {
  email: string;
  isActive: boolean;
  isExternal: boolean;
  savingStatus: boolean;
  onDisable: () => void;
  onEnable: () => void;
  onCopyResetLink: () => void;
}

export function AccountStatusCard({
  email,
  isActive,
  isExternal,
  savingStatus,
  onDisable,
  onEnable,
  onCopyResetLink,
}: Props) {
  const { t } = useT();
  return (
    <Card className="border-border">
      <CardContent className="pt-5">
        <SectionTitle>{t(keys.users.account_status.title)}</SectionTitle>
        <div className="mb-3 flex items-center gap-2">
          <Badge
            variant="outline"
            className={
              isActive
                ? 'border-primary-200 bg-primary-50 text-primary-700'
                : 'border-border bg-secondary text-muted-foreground'
            }
          >
            {isActive ? t(keys.users.account_status.active) : t(keys.users.account_status.disabled)}
          </Badge>
          {isExternal && (
            <Badge variant="outline" className="border-violet-200 bg-violet-50 text-violet-700">
              {t(keys.users.common.external_badge)}
            </Badge>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {isActive ? (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" size="sm" disabled={savingStatus}>
                  {savingStatus
                    ? t(keys.users.common.saving)
                    : t(keys.users.account_status.disable_button)}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>
                    {t(keys.users.account_status.disable_confirm_title, { email })}
                  </AlertDialogTitle>
                  <AlertDialogDescription>
                    {t(keys.users.account_status.disable_confirm_body)}
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>{t(keys.users.common.cancel)}</AlertDialogCancel>
                  <AlertDialogAction onClick={onDisable}>
                    {t(keys.users.account_status.disable_action)}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          ) : (
            <Button size="sm" onClick={onEnable} disabled={savingStatus}>
              {savingStatus
                ? t(keys.users.common.saving)
                : t(keys.users.account_status.enable_button)}
            </Button>
          )}
          {!isExternal && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="outline" size="sm" className="gap-1.5">
                  <Copy className="h-3.5 w-3.5" />
                  {t(keys.users.account_status.copy_reset_link)}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>
                    {t(keys.users.account_status.reset_confirm_title, { email })}
                  </AlertDialogTitle>
                  <AlertDialogDescription>
                    {t(keys.users.account_status.reset_confirm_body)}
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>{t(keys.users.common.cancel)}</AlertDialogCancel>
                  <AlertDialogAction onClick={onCopyResetLink}>
                    {t(keys.users.account_status.reset_action)}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>
        {isExternal && (
          <p className="mt-3 text-sm text-muted-foreground">
            {t(keys.users.account_status.external_note)}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
