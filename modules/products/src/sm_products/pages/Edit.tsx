import { Link, useForm, usePage } from '@inertiajs/react';
import { PageShell } from '@ui/components/PageShell';
import { AuthenticatedLayout } from '@ui/layouts/AuthenticatedLayout';

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

  const { data, setData, put, processing, errors } = useForm({
    name: product.name,
    description: product.description || '',
    price: product.price,
    is_active: product.is_active,
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    put(`/api/products/${product.id}`);
  }

  return (
    <PageShell
      title={`Edit: ${product.name}`}
      description="Update product details"
      actions={
        <Link href="/products" className="btn-secondary">
          Back to Products
        </Link>
      }
    >
      <div className="card max-w-xl">
        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          <div>
            <label htmlFor="name" className="label">
              Name
            </label>
            <input
              id="name"
              type="text"
              value={data.name}
              onChange={(e) => setData('name', e.target.value)}
              className="input"
            />
            {errors.name && <p className="text-sm text-red-600 mt-1.5">{errors.name}</p>}
          </div>
          <div>
            <label htmlFor="description" className="label">
              Description
            </label>
            <textarea
              id="description"
              value={data.description}
              onChange={(e) => setData('description', e.target.value)}
              className="input"
              rows={4}
            />
          </div>
          <div>
            <label htmlFor="price" className="label">
              Price
            </label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">
                $
              </span>
              <input
                id="price"
                type="number"
                step="0.01"
                value={data.price}
                onChange={(e) => setData('price', e.target.value)}
                className="input pl-7"
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <input
              id="is_active"
              type="checkbox"
              checked={data.is_active}
              onChange={(e) => setData('is_active', e.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
            />
            <label htmlFor="is_active" className="text-sm text-gray-700">
              Active
            </label>
          </div>
          <div className="pt-2 flex gap-3">
            <button type="submit" disabled={processing} className="btn-primary">
              {processing ? 'Saving...' : 'Save Changes'}
            </button>
            <Link href="/products" className="btn-secondary">
              Cancel
            </Link>
          </div>
        </form>
      </div>
    </PageShell>
  );
}

Edit.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Edit;
