import { Button } from '@ui/components/ui/button';
import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  /** Callback fired when an error is caught. Useful for error tracking. */
  onError?: (error: Error, info: ErrorInfo) => void;
  /** Optional custom fallback UI. Receives the error and a reset function. */
  fallback?: (error: Error, reset: () => void) => ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    this.props.onError?.(error, info);
    if (import.meta.env.DEV) {
      console.error('ErrorBoundary caught:', error, info);
    }
  }

  reset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;
    if (error === null) return this.props.children;

    if (this.props.fallback) return this.props.fallback(error, this.reset);

    return <DefaultFallback error={error} reset={this.reset} />;
  }
}

function DefaultFallback({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="text-center max-w-md">
        <p className="text-8xl font-extrabold font-[var(--font-display)] text-primary">!</p>
        <h1 className="mt-4 text-3xl font-bold tracking-tight text-foreground font-[var(--font-display)] sm:text-4xl">
          Something went wrong
        </h1>
        <p className="mt-3 text-base text-muted-foreground leading-relaxed">
          The page encountered an unexpected error. Try reloading, or return home.
        </p>
        {import.meta.env.DEV && (
          <pre className="mt-4 text-left text-xs bg-muted p-3 rounded overflow-auto max-h-48 text-destructive">
            {error.message}
            {error.stack ? `\n\n${error.stack}` : ''}
          </pre>
        )}
        <div className="mt-8 flex items-center justify-center gap-4">
          <Button
            onClick={() => {
              reset();
              window.location.reload();
            }}
          >
            Reload Page
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              reset();
              window.location.href = '/';
            }}
          >
            Go Home
          </Button>
        </div>
      </div>
    </div>
  );
}
