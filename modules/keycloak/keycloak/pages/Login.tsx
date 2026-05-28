import { router } from '@inertiajs/react';
import { useEffect } from 'react';

export default function Login() {
  useEffect(() => {
    router.get('/api/keycloak/auth/login');
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-muted-foreground">Redirecting to identity provider...</p>
    </div>
  );
}
