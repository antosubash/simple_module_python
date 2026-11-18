import { usePage } from '@inertiajs/react';
import { type ComponentType, createElement, type ReactNode } from 'react';

interface AdminSurface {
  prefix: string;
  layout: ComponentType<{ children: ReactNode }>;
}

type PageModule = {
  default: ComponentType<Record<string, unknown>> & { layout?: unknown };
};

function SurfaceLayout({ children, surface }: { children?: ReactNode; surface: AdminSurface }) {
  const page = usePage();
  const path = new URL(page.url, 'http://inertia.local').pathname;
  const admin = path === surface.prefix || path.startsWith(`${surface.prefix}/`);
  return admin ? createElement(surface.layout, null, children) : children;
}

/** Generated loaders supply defaults even in hosts with an older page resolver. */
export function withAdminSurface<T extends PageModule>(
  pages: Record<string, () => Promise<T>>,
  surface: AdminSurface,
): Record<string, () => Promise<T>> {
  const layout = (page: ReactNode) => createElement(SurfaceLayout, { surface }, page);

  return Object.fromEntries(
    Object.entries(pages).map(([path, load]) => [
      path,
      async () => {
        const module = await load();
        if (module.default.layout === undefined) module.default.layout = layout;
        return module;
      },
    ]),
  );
}
