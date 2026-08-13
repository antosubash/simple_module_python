import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';

interface Props {
  email: string;
  fullName: string;
  onEmailChange: (value: string) => void;
  onFullNameChange: (value: string) => void;
  error?: string | null;
}

/**
 * Editable account details. Fully controlled and without a save button of its
 * own — the page owns one dirty state covering details and roles together.
 */
export function DetailsCard({ email, fullName, onEmailChange, onFullNameChange, error }: Props) {
  return (
    <Card className="border-border lg:col-span-2">
      <CardContent className="pt-5">
        <SectionTitle>Details</SectionTitle>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="edit-email" className="text-sm font-medium text-muted-foreground">
              Email
            </Label>
            <Input
              id="edit-email"
              type="email"
              value={email}
              onChange={(e) => onEmailChange(e.target.value)}
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
              onChange={(e) => onFullNameChange(e.target.value)}
              placeholder="Jane Doe"
            />
          </div>
        </div>
        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  );
}
