import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { useState } from 'react';
import { toast } from 'sonner';

interface Props {
  user: { id: string; email: string; full_name: string | null };
}

export function DetailsCard({ user }: Props) {
  const [email, setEmail] = useState(user.email);
  const [fullName, setFullName] = useState(user.full_name ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = () => {
    setSaving(true);
    setError(null);
    fetch(`/api/users/admin/${user.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, full_name: fullName || null }),
    })
      .then(async (res) => {
        if (res.ok) {
          toast.success('Details updated');
        } else {
          const data = await res.json().catch(() => ({}));
          setError(typeof data?.detail === 'string' ? data.detail : 'Failed to update details');
        }
      })
      .catch(() => setError('An error occurred'))
      .finally(() => setSaving(false));
  };

  return (
    <Card className="border-border lg:col-span-2">
      <CardContent className="pt-5">
        <SectionTitle
          right={
            <Button size="sm" onClick={handleSave} disabled={saving}>
              {saving ? 'Saving…' : 'Save details'}
            </Button>
          }
        >
          Details
        </SectionTitle>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="edit-email" className="text-sm font-medium text-muted-foreground">
              Email
            </Label>
            <Input
              id="edit-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="off"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="edit-full-name" className="text-sm font-medium text-muted-foreground">
              Full name
            </Label>
            <Input
              id="edit-full-name"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Jane Doe"
            />
          </div>
        </div>
        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  );
}
