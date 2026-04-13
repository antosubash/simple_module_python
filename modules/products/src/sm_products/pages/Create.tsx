import { Link, useForm } from '@inertiajs/react';
import { PageShell } from '@ui/components/PageShell';
import { Button } from '@ui/components/ui/button';
import { Card, CardContent } from '@ui/components/ui/card';
import { Input } from '@ui/components/ui/input';
import { Label } from '@ui/components/ui/label';
import { Textarea } from '@ui/components/ui/textarea';
import { AuthenticatedLayout } from '@ui/layouts/AuthenticatedLayout';
import { toast } from 'sonner';
import { validateProduct } from '../validation';

function Create() {
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
      onSuccess: () => toast.success('Product created'),
      onError: (errs) => {
        const first = Object.values(errs)[0];
        if (first) toast.error(first);
      },
    });
  }

  return (
    <PageShell
      title="Create Product"
      description="Add a new product to the catalog"
      actions={
        <Button asChild variant="outline">
          <Link href="/products">Cancel</Link>
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
                placeholder="Enter product name"
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
                placeholder="Optional description"
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
                  placeholder="0.00"
                  required
                />
              </div>
              {errors.price && <p className="text-sm text-destructive">{errors.price}</p>}
            </div>

            <div className="pt-2 flex gap-3">
              <Button type="submit" disabled={processing}>
                {processing ? 'Creating...' : 'Create Product'}
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

Create.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Create;
