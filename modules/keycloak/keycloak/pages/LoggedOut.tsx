import { Link } from '@inertiajs/react';

export default function LoggedOut() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4">
      <h1 className="text-2xl font-bold">Signed Out</h1>
      <p className="text-muted-foreground">You have been signed out successfully.</p>
      <Link href="/keycloak/login" className="text-primary underline">
        Sign in again
      </Link>
    </div>
  );
}
