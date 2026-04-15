import { ErrorScreen } from '@simple-module/ui/components/ErrorScreen';
import { Button } from '@simple-module/ui/components/ui/button';
import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  /** Useful for error tracking (Sentry, etc). */
  onError?: (error: Error, info: ErrorInfo) => void;
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
    if (this.state.error !== null) this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;
    if (error === null) return this.props.children;
    if (this.props.fallback) return this.props.fallback(error, this.reset);
    return <DefaultFallback error={error} />;
  }
}

function DefaultFallback({ error }: { error: Error }) {
  const details = import.meta.env.DEV ? (
    <pre className="mt-4 text-left text-xs bg-muted p-3 rounded overflow-auto max-h-48 text-destructive">
      {[error.message, error.stack].filter(Boolean).join('\n\n')}
    </pre>
  ) : undefined;

  return (
    <ErrorScreen
      hero="!"
      title="Something went wrong"
      description="The page encountered an unexpected error. Try reloading, or return home."
      details={details}
    >
      {/* Full reload — React tree is broken, Inertia navigation won't recover. */}
      <Button onClick={() => window.location.reload()}>Reload Page</Button>
      <Button
        variant="outline"
        onClick={() => {
          window.location.href = '/';
        }}
      >
        Go Home
      </Button>
    </ErrorScreen>
  );
}
