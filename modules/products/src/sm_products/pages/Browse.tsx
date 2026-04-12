import { usePage, Link } from '@inertiajs/react';
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
    products: Product[];
}

function Browse() {
    const { products } = usePage<{ props: Props }>().props as unknown as Props;

    return (
        <PageShell
            title="Products"
            description="Manage your product catalog"
            actions={
                <Link href="/products/create" className="btn-primary">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                    </svg>
                    New Product
                </Link>
            }
        >
            <div className="card overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50/50">
                            <tr>
                                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider sm:px-6 sm:py-3.5">Name</th>
                                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider sm:px-6 sm:py-3.5">Price</th>
                                <th className="hidden px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider sm:table-cell sm:px-6 sm:py-3.5">Status</th>
                                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider sm:px-6 sm:py-3.5">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                            {products.map((product) => (
                                <tr key={product.id} className="hover:bg-gray-50/50 transition-colors">
                                    <td className="px-4 py-3 sm:px-6 sm:py-4">
                                        <span className="text-sm font-medium text-gray-900">{product.name}</span>
                                        {/* Show status inline on mobile */}
                                        <span className={`inline-block mt-1 sm:hidden ${product.is_active ? 'badge-success' : 'badge-danger'}`}>
                                            {product.is_active ? 'Active' : 'Inactive'}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3 sm:px-6 sm:py-4">
                                        <span className="text-sm text-gray-600">${product.price}</span>
                                    </td>
                                    <td className="hidden px-4 py-3 sm:table-cell sm:px-6 sm:py-4">
                                        <span className={product.is_active ? 'badge-success' : 'badge-danger'}>
                                            {product.is_active ? 'Active' : 'Inactive'}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3 text-right sm:px-6 sm:py-4">
                                        <Link
                                            href={`/products/${product.id}/edit`}
                                            className="btn-ghost text-xs"
                                        >
                                            Edit
                                        </Link>
                                    </td>
                                </tr>
                            ))}
                            {products.length === 0 && (
                                <tr>
                                    <td colSpan={4} className="px-4 py-12 text-center sm:px-6 sm:py-16">
                                        <div className="flex flex-col items-center">
                                            <svg className="w-12 h-12 text-gray-300 mb-4" fill="none" viewBox="0 0 24 24" strokeWidth={1} stroke="currentColor">
                                                <path strokeLinecap="round" strokeLinejoin="round" d="m21 7.5-9-5.25L3 7.5m18 0-9 5.25m9-5.25v9l-9 5.25M3 7.5l9 5.25M3 7.5v9l9 5.25m0-9v9" />
                                            </svg>
                                            <p className="text-sm font-medium text-gray-900">No products yet</p>
                                            <p className="text-sm text-gray-500 mt-1">Get started by creating your first product.</p>
                                            <Link href="/products/create" className="btn-primary mt-4 text-xs">
                                                Create Product
                                            </Link>
                                        </div>
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </PageShell>
    );
}

Browse.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Browse;
