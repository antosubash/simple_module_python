import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import type React from 'react';
import { useState } from 'react';
import { useTenantErrors } from '../hooks/useTenantErrors';

interface Props {
  /** Called after the API confirms creation, so the page can reload its props. */
  onCreated: () => void;
}

/** The self-service "create an organisation" form on the Index page. */
export function CreateOrgForm({ onCreated }: Props) {
  const { t } = useT();
  const { describe } = useTenantErrors();
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch('/api/tenants/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ name, slug: slug || undefined }),
      });
      if (!response.ok) {
        setError(await describe(response));
        return;
      }
      setName('');
      setSlug('');
      onCreated();
    } catch {
      setError(t(keys.tenants.errors.generic));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t(keys.tenants.index.create_title)}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="org-name">{t(keys.tenants.index.create_name_label)}</Label>
            <Input
              id="org-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t(keys.tenants.index.create_name_placeholder)}
              required
              maxLength={200}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="org-slug">{t(keys.tenants.index.create_slug_label)}</Label>
            <Input
              id="org-slug"
              value={slug}
              onChange={(e) => setSlug(e.target.value.toLowerCase())}
              placeholder={t(keys.tenants.index.create_slug_placeholder)}
              maxLength={50}
            />
            <p className="text-xs text-muted-foreground">
              {t(keys.tenants.index.create_slug_hint)}
            </p>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" disabled={submitting || !name.trim()} className="max-lg:min-h-11">
            {submitting
              ? t(keys.tenants.index.create_submitting)
              : t(keys.tenants.index.create_submit)}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
