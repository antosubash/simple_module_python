import type { ErrorInfo } from 'react';

/** Shared reporting point for client errors; integrations can forward to their tracker here. */
export function reportClientError(error: Error, info: ErrorInfo): void {
  console.error('ErrorBoundary caught:', error, info);
}
