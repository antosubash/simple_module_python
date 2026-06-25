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
  return (
    <Card className="border-border">
      <CardContent className="pt-5">
        <SectionTitle>Account status</SectionTitle>
        <div className="mb-3 flex items-center gap-2">
          <Badge
            variant="outline"
            className={
              isActive
                ? 'border-primary-200 bg-primary-50 text-primary-700'
                : 'border-border bg-secondary text-muted-foreground'
            }
          >
            {isActive ? 'active' : 'disabled'}
          </Badge>
          {isExternal && (
            <Badge variant="outline" className="border-violet-200 bg-violet-50 text-violet-700">
              External · SSO
            </Badge>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {isActive ? (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" size="sm" disabled={savingStatus}>
                  {savingStatus ? 'Saving…' : 'Disable account'}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Disable {email}?</AlertDialogTitle>
                  <AlertDialogDescription>
                    They won't be able to sign in until you re-enable the account.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={onDisable}>Disable</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          ) : (
            <Button size="sm" onClick={onEnable} disabled={savingStatus}>
              {savingStatus ? 'Saving…' : 'Enable account'}
            </Button>
          )}
          {!isExternal && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="outline" size="sm" className="gap-1.5">
                  <Copy className="h-3.5 w-3.5" />
                  Copy reset link
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Generate reset link for {email}?</AlertDialogTitle>
                  <AlertDialogDescription>
                    A one-time password-reset URL will be copied to your clipboard. Any previously
                    issued reset link for this user will be invalidated.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={onCopyResetLink}>Generate</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>
        {isExternal && (
          <p className="mt-3 text-sm text-muted-foreground">
            This account signs in through an external identity provider (SSO) and has no password,
            so there's no reset link to generate.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
