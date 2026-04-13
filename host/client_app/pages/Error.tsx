import { Link } from '@inertiajs/react';
import { Button } from '@ui/components/ui/button';

interface Props {
  status: number;
  message: string;
}

const titles: Record<number, string> = {
  403: 'Forbidden',
  404: 'Page Not Found',
  500: 'Server Error',
};

const descriptions: Record<number, string> = {
  403: "You don't have permission to access this page.",
  404: "The page you're looking for doesn't exist or has been moved.",
  500: 'Something went wrong on our end. Please try again later.',
};

function Error({ status, message }: Props) {
  const title = titles[status] || 'Error';
  const description = message || descriptions[status] || 'An unexpected error occurred.';

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="text-center max-w-md">
        <p className="text-8xl font-extrabold font-[var(--font-display)] text-primary">{status}</p>
        <h1 className="mt-4 text-3xl font-bold tracking-tight text-foreground font-[var(--font-display)] sm:text-4xl">
          {title}
        </h1>
        <p className="mt-3 text-base text-muted-foreground leading-relaxed">{description}</p>
        <div className="mt-8 flex items-center justify-center gap-4">
          <Button asChild>
            <Link href="/">Go Home</Link>
          </Button>
          <Button variant="outline" onClick={() => window.history.back()}>
            Go Back
          </Button>
        </div>
      </div>
    </div>
  );
}

export default Error;
