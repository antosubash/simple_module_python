import { Link, useForm } from '@inertiajs/react';
import { keys, useT } from '@simple-module/i18n';
import { PageShell } from '@simple-module/ui/components/PageShell';
import { Button } from '@simple-module/ui/components/ui/button';
import { Card, CardContent } from '@simple-module/ui/components/ui/card';
import { Input } from '@simple-module/ui/components/ui/input';
import { Label } from '@simple-module/ui/components/ui/label';
import { Textarea } from '@simple-module/ui/components/ui/textarea';
import { AuthenticatedLayout } from '@simple-module/ui/layouts/AuthenticatedLayout';
import { toast } from 'sonner';
import { useValidateProduct } from './validation';

function Create() {
  const { t } = useT();
  const validateProduct = useValidateProduct();
  const { data, setData, post, processing, errors, clearErrors } = useForm({
    name: '',
    description: '',
    price: '',
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const clientErrors = validateProduct(data);
    if (Object.keys(clientErrors).length > 0) {
      for (const msg of Object.values(clientErrors)) {
        toast.error(msg);
      }
      return;
    }
    post('/products', {
      onSuccess: () => toast.success(t(keys.products.toasts.created)),
      onError: (errs) => {
        const first = Object.values(errs)[0];
        if (first) toast.error(first);
      },
    });
  }

  return (
    <PageShell
      title={t(keys.products.create.title)}
      description={t(keys.products.create.description)}
      actions={
        <Button asChild variant="outline">
          <Link href="/products">{t(keys.products.form.cancel_button)}</Link>
        </Button>
      }
    >
      <Card className="max-w-xl">
        <CardContent className="pt-6">
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="name">
                {t(keys.products.form.name_label)} <span className="text-destructive">*</span>
              </Label>
              <Input
                id="name"
                type="text"
                value={data.name}
                onChange={(e) => {
                  setData('name', e.target.value);
                  clearErrors('name');
                }}
                placeholder={t(keys.products.form.name_placeholder)}
                maxLength={200}
                required
              />
              {errors.name && <p className="text-sm text-destructive">{errors.name}</p>}
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">{t(keys.products.form.description_label)}</Label>
              <Textarea
                id="description"
                value={data.description}
                onChange={(e) => setData('description', e.target.value)}
                rows={4}
                placeholder={t(keys.products.form.description_placeholder)}
                maxLength={2000}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="price">
                {t(keys.products.form.price_label)} <span className="text-destructive">*</span>
              </Label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">
                  $
                </span>
                <Input
                  id="price"
                  type="number"
                  step="0.01"
                  min="0.01"
                  value={data.price}
                  onChange={(e) => {
                    setData('price', e.target.value);
                    clearErrors('price');
                  }}
                  className="pl-7"
                  placeholder={t(keys.products.form.price_placeholder)}
                  required
                />
              </div>
              {errors.price && <p className="text-sm text-destructive">{errors.price}</p>}
            </div>

            <div className="pt-2 flex gap-3">
              <Button type="submit" disabled={processing}>
                {processing
                  ? t(keys.products.create.submitting_button)
                  : t(keys.products.create.submit_button)}
              </Button>
              <Button asChild variant="outline">
                <Link href="/products">{t(keys.products.form.cancel_button)}</Link>
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </PageShell>
  );
}

Create.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Create;
