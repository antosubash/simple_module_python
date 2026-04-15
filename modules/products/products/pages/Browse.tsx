import { Link, router, usePage } from '@inertiajs/react';
import { PageShell } from '@simple-module/ui/components/PageShell';
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
} from '@simple-module/ui/components/ui/alert-dialog';
import { Badge } from '@simple-module/ui/components/ui/badge';
import { Button } from '@simple-module/ui/components/ui/button';
import { Card } from '@simple-module/ui/components/ui/card';
import { Empty, EmptyDescription, EmptyMedia, EmptyTitle } from '@simple-module/ui/components/ui/empty';
import { Input } from '@simple-module/ui/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module/ui/components/ui/table';
import { usePermissions } from '@simple-module/ui/hooks/use-permissions';
import { AuthenticatedLayout } from '@simple-module/ui/layouts/AuthenticatedLayout';
import { Package, Pencil, Plus, Search, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { ProductsPagination } from './components/ProductsPagination';

interface Product {
  id: number;
  name: string;
  description: string | null;
  price: string;
  is_active: boolean;
}

interface PaginationData {
  page: number;
  perPage: number;
  total: number;
}

interface Props {
  products: Product[];
  pagination: PaginationData;
  search: string;
}

function Browse() {
  const {
    products,
    pagination,
    search: initialSearch,
  } = usePage<{ props: Props }>().props as unknown as Props;
  const { can } = usePermissions();
  const canCreate = can('products.create');
  const canEdit = can('products.edit');
  const canDelete = can('products.delete');
  const [search, setSearch] = useState(initialSearch || '');

  const totalPages = useMemo(
    () => Math.ceil(pagination.total / pagination.perPage),
    [pagination.total, pagination.perPage],
  );

  function navigate(page: number, q?: string) {
    const params: Record<string, string> = {};
    const query = q ?? search;
    if (query) params.q = query;
    if (page > 1) params.page = String(page);
    router.get('/products', params, { preserveState: true, preserveScroll: true });
  }

  // Debounced server-side search
  useEffect(() => {
    if (search === (initialSearch || '')) return;
    const timeout = setTimeout(() => navigate(1, search), 300);
    return () => clearTimeout(timeout);
  }, [search, initialSearch]);

  function handleDelete(product: Product) {
    router.delete(`/products/${product.id}`, {
      onSuccess: () => toast.success(`"${product.name}" deleted`),
      onError: () => toast.error('Failed to delete product'),
    });
  }

  return (
    <PageShell
      title="Products"
      description="Manage your product catalog"
      actions={
        canCreate ? (
          <Button asChild>
            <Link href="/products/create">
              <Plus />
              New Product
            </Link>
          </Button>
        ) : undefined
      }
    >
      {/* Search bar */}
      <div className="mb-4 flex items-center justify-between gap-4">
        <div className="relative max-w-sm flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input
            placeholder="Search products..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        {pagination.total > 0 && (
          <p className="text-sm text-muted-foreground whitespace-nowrap">
            {pagination.total} product{pagination.total !== 1 ? 's' : ''}
          </p>
        )}
      </div>

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="sm:px-6">Name</TableHead>
              <TableHead className="hidden md:table-cell sm:px-6">Description</TableHead>
              <TableHead className="sm:px-6">Price</TableHead>
              <TableHead className="hidden sm:table-cell sm:px-6">Status</TableHead>
              {(canEdit || canDelete) && (
                <TableHead className="text-right sm:px-6">Actions</TableHead>
              )}
            </TableRow>
          </TableHeader>
          <TableBody>
            {products.map((product) => (
              <TableRow key={product.id}>
                <TableCell className="sm:px-6">
                  <div>
                    <span className="font-medium">{product.name}</span>
                    <span className="inline-block mt-1 sm:hidden">
                      <Badge variant={product.is_active ? 'secondary' : 'destructive'}>
                        {product.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </span>
                  </div>
                </TableCell>
                <TableCell className="hidden md:table-cell sm:px-6">
                  <span className="text-muted-foreground text-sm line-clamp-1">
                    {product.description || '—'}
                  </span>
                </TableCell>
                <TableCell className="sm:px-6">
                  <span className="tabular-nums text-muted-foreground">${product.price}</span>
                </TableCell>
                <TableCell className="hidden sm:table-cell sm:px-6">
                  <Badge variant={product.is_active ? 'secondary' : 'destructive'}>
                    {product.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                </TableCell>
                {(canEdit || canDelete) && (
                  <TableCell className="text-right sm:px-6">
                    <div className="flex items-center justify-end gap-1">
                      {canEdit && (
                        <Button asChild variant="ghost" size="icon-sm">
                          <Link href={`/products/${product.id}/edit`}>
                            <Pencil />
                          </Link>
                        </Button>
                      )}
                      {canDelete && (
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              className="text-destructive hover:text-destructive"
                            >
                              <Trash2 />
                            </Button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>Delete "{product.name}"?</AlertDialogTitle>
                              <AlertDialogDescription>
                                This action cannot be undone. This will permanently delete the
                                product from the catalog.
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>Cancel</AlertDialogCancel>
                              <AlertDialogAction
                                onClick={() => handleDelete(product)}
                                className="bg-destructive text-white hover:bg-destructive/90"
                              >
                                Delete
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      )}
                    </div>
                  </TableCell>
                )}
              </TableRow>
            ))}
            {products.length === 0 && pagination.total === 0 && !search && (
              <TableRow>
                <TableCell colSpan={5} className="h-40">
                  <Empty>
                    <EmptyMedia variant="icon">
                      <Package className="size-5 text-primary-300" />
                    </EmptyMedia>
                    <EmptyTitle>No products yet</EmptyTitle>
                    <EmptyDescription>Get started by creating your first product.</EmptyDescription>
                    <Button asChild size="sm" className="mt-2">
                      <Link href="/products/create">Create Product</Link>
                    </Button>
                  </Empty>
                </TableCell>
              </TableRow>
            )}
            {products.length === 0 && search && (
              <TableRow>
                <TableCell colSpan={5} className="h-32">
                  <Empty>
                    <EmptyMedia variant="icon">
                      <Search className="size-5" />
                    </EmptyMedia>
                    <EmptyDescription>No products match "{search}"</EmptyDescription>
                  </Empty>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>

      <ProductsPagination
        page={pagination.page}
        totalPages={totalPages}
        onNavigate={(p) => navigate(p)}
      />
    </PageShell>
  );
}

Browse.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Browse;
