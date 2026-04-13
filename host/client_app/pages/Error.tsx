import { Link } from '@inertiajs/react';

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
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="text-center max-w-md">
        <p className="text-8xl font-extrabold text-primary-500">{status}</p>
        <h1 className="mt-4 text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
          {title}
        </h1>
        <p className="mt-3 text-base text-gray-600 leading-relaxed">{description}</p>
        <div className="mt-8 flex items-center justify-center gap-4">
          <Link href="/" className="btn-primary px-5 py-2.5">
            Go Home
          </Link>
          <button
            type="button"
            onClick={() => window.history.back()}
            className="btn-secondary px-5 py-2.5"
          >
            Go Back
          </button>
        </div>
      </div>
    </div>
  );
}

export default Error;
