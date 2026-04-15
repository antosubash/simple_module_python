import type React from 'react';

/**
 * Full-viewport centered-card shell for unauthenticated flows
 * (login, register, password reset, email verify, invite accept).
 *
 * Distinct from PublicLayout (branded landing nav + footer) and
 * AuthenticatedLayout (sidebar shell): auth-form pages want a minimal
 * undecorated centering wrapper with nothing else on the page.
 */
export function AuthCardShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-muted p-4">
      {children}
    </div>
  );
}
