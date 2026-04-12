import { useForm, Link } from '@inertiajs/react';
import { PageShell } from '@ui/components/PageShell';
import { AuthenticatedLayout } from '@ui/layouts/AuthenticatedLayout';

function Create() {
    const { data, setData, post, processing, errors } = useForm({
        name: '',
        description: '',
        price: '',
    });

    function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        post('/api/products');
    }

    return (
        <PageShell
            title="Create Product"
            description="Add a new product to the catalog"
            actions={
                <Link href="/products" className="btn-secondary">
                    Cancel
                </Link>
            }
        >
            <div className="card max-w-xl">
                <form onSubmit={handleSubmit} className="p-6 space-y-5">
                    <div>
                        <label htmlFor="name" className="label">Name</label>
                        <input
                            id="name"
                            type="text"
                            value={data.name}
                            onChange={e => setData('name', e.target.value)}
                            className="input"
                            placeholder="Enter product name"
                        />
                        {errors.name && <p className="text-sm text-red-600 mt-1.5">{errors.name}</p>}
                    </div>
                    <div>
                        <label htmlFor="description" className="label">Description</label>
                        <textarea
                            id="description"
                            value={data.description}
                            onChange={e => setData('description', e.target.value)}
                            className="input"
                            rows={4}
                            placeholder="Optional description"
                        />
                    </div>
                    <div>
                        <label htmlFor="price" className="label">Price</label>
                        <div className="relative">
                            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
                            <input
                                id="price"
                                type="number"
                                step="0.01"
                                min="0"
                                value={data.price}
                                onChange={e => setData('price', e.target.value)}
                                className="input pl-7"
                                placeholder="0.00"
                            />
                        </div>
                        {errors.price && <p className="text-sm text-red-600 mt-1.5">{errors.price}</p>}
                    </div>
                    <div className="pt-2 flex gap-3">
                        <button type="submit" disabled={processing} className="btn-primary">
                            {processing ? 'Creating...' : 'Create Product'}
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

Create.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Create;
