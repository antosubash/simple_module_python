import { Link } from '@inertiajs/react';
import { ErrorScreen } from '@ui/components/ErrorScreen';
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

function ErrorPage({ status, message }: Props) {
  const title = titles[status] || 'Error';
  const description = message || descriptions[status] || 'An unexpected error occurred.';

  return (
    <ErrorScreen hero={status} title={title} description={description}>
      <Button asChild>
        <Link href="/">Go Home</Link>
      </Button>
      <Button variant="outline" onClick={() => window.history.back()}>
        Go Back
      </Button>
    </ErrorScreen>
  );
}

export default ErrorPage;
