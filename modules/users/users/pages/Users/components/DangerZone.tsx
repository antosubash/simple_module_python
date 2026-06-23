import { router } from '@inertiajs/react';
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
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { Trash2 } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';

interface Props {
  userId: string;
  email: string;
  isSelf: boolean;
}

export function DangerZone({ userId, email, isSelf }: Props) {
  const [deleting, setDeleting] = useState(false);

  const handleDelete = () => {
    setDeleting(true);
    fetch(`/api/users/admin/${userId}`, { method: 'DELETE' })
      .then(async (res) => {
        if (res.ok) {
          toast.success('User deleted');
          router.visit('/users/admin');
          return; // navigating away — leave `deleting` set
        }
        const data = await res.json().catch(() => ({}));
        toast.error(typeof data?.detail === 'string' ? data.detail : 'Failed to delete user');
        setDeleting(false);
      })
      .catch(() => {
        toast.error('An error occurred');
        setDeleting(false);
      });
  };

  return (
    <Card className="border-destructive/40 lg:col-span-2">
      <CardContent className="pt-5">
        <SectionTitle>Danger zone</SectionTitle>
        {isSelf ? (
          <p className="text-sm text-muted-foreground">You cannot delete your own account.</p>
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-sm text-muted-foreground">
              Permanently delete this user. This cannot be undone.
            </p>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" size="sm" className="gap-1.5" disabled={deleting}>
                  <Trash2 className="h-3.5 w-3.5" />
                  {deleting ? 'Deleting…' : 'Delete user'}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete {email}?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This permanently removes the account and all of its access. This action cannot
                    be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleDelete}>Delete</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
