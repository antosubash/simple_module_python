import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from '@ui/components/ui/pagination';

interface Props {
  page: number;
  totalPages: number;
  onNavigate: (page: number) => void;
}

export function ProductsPagination({ page, totalPages, onNavigate }: Props) {
  if (totalPages <= 1) return null;

  const items = Array.from({ length: totalPages }, (_, i) => i + 1)
    .filter((p) => p === 1 || p === totalPages || Math.abs(p - page) <= 1)
    .reduce<(number | 'ellipsis')[]>((acc, p, i, arr) => {
      if (i > 0 && p - (arr[i - 1] as number) > 1) acc.push('ellipsis');
      acc.push(p);
      return acc;
    }, []);

  return (
    <div className="mt-4">
      <Pagination>
        <PaginationContent>
          <PaginationItem>
            <PaginationPrevious
              onClick={() => onNavigate(page - 1)}
              className={page <= 1 ? 'pointer-events-none opacity-50' : 'cursor-pointer'}
            />
          </PaginationItem>
          {items.map((item, i) =>
            item === 'ellipsis' ? (
              <PaginationItem key={`e${i}`}>
                <PaginationEllipsis />
              </PaginationItem>
            ) : (
              <PaginationItem key={item}>
                <PaginationLink
                  isActive={item === page}
                  onClick={() => onNavigate(item)}
                  className="cursor-pointer"
                >
                  {item}
                </PaginationLink>
              </PaginationItem>
            ),
          )}
          <PaginationItem>
            <PaginationNext
              onClick={() => onNavigate(page + 1)}
              className={page >= totalPages ? 'pointer-events-none opacity-50' : 'cursor-pointer'}
            />
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    </div>
  );
}
