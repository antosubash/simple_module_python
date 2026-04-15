import { Link, useForm, usePage } from '@inertiajs/react';
import { PageShell } from '@simple-module/ui/components/PageShell';
import { Button } from '@simple-module/ui/components/ui/button';
import { Card, CardContent } from '@simple-module/ui/components/ui/card';
import { Checkbox } from '@simple-module/ui/components/ui/checkbox';
import { Input } from '@simple-module/ui/components/ui/input';
import { Label } from '@simple-module/ui/components/ui/label';
import { Textarea } from '@simple-module/ui/components/ui/textarea';
import { AuthenticatedLayout } from '@simple-module/ui/layouts/AuthenticatedLayout';
import { toast } from 'sonner';
import { validateProduct } from './validation';

interface Product {
  id: number;
  name: string;
  description: string | null;
  price: string;
  is_active: boolean;
}

interface Props {
  product: Product;
}

function Edit() {
  const { product } = usePage<{ props: Props }>().props as unknown as Props;

  const { data, setData, put, processing, errors, clearErrors } = useForm({
    name: product.name,
    description: product.description || '',
    price: product.price,
    is_active: product.is_active,
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
    put(`/products/${product.id}`, {
      onSuccess: () => toast.success('Product updated'),
      onError: (errs) => {
        const first = Object.values(errs)[0];
        if (first) toast.error(first);
      },
    });
  }

  return (
    <PageShell
      title={`Edit: ${product.name}`}
      description="Update product details"
      actions={
        <Button asChild variant="outline">
          <Link href="/products">Back to Products</Link>
        </Button>
      }
    >
      <Card className="max-w-xl">
        <CardContent className="pt-6">
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="name">
                Name <span className="text-destructive">*</span>
              </Label>
              <Input
                id="name"
                type="text"
                value={data.name}
                onChange={(e) => {
                  setData('name', e.target.value);
                  clearErrors('name');
                }}
                maxLength={200}
                required
              />
              {errors.name && <p className="text-sm text-destructive">{errors.name}</p>}
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">Description</Label>
              <Textarea
                id="description"
                value={data.description}
                onChange={(e) => setData('description', e.target.value)}
                rows={4}
                maxLength={2000}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="price">
                Price <span className="text-destructive">*</span>
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
                  required
                />
              </div>
              {errors.price && <p className="text-sm text-destructive">{errors.price}</p>}
            </div>

            <div className="flex items-center gap-3">
              <Checkbox
                id="is_active"
                checked={data.is_active}
                onCheckedChange={(checked) => setData('is_active', checked === true)}
              />
              <Label htmlFor="is_active" className="cursor-pointer">
                Active
              </Label>
            </div>

            <div className="pt-2 flex gap-3">
              <Button type="submit" disabled={processing}>
                {processing ? 'Saving...' : 'Save Changes'}
              </Button>
              <Button asChild variant="outline">
                <Link href="/products">Cancel</Link>
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </PageShell>
  );
}

Edit.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Edit;
