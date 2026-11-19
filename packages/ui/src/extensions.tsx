import { usePage } from '@inertiajs/react';
import { createContext, type ReactNode, Suspense, useContext } from 'react';
import { ExtensionRegistry, extensions } from './extension-registry';
import type { ExtensionSlots } from './extension-types';

export type {
  ExtensionSlots,
  FieldType,
  LayoutComponents,
  MenuIcon,
  SettingsFieldMeta,
  SettingsFieldRendererProps,
  SlotContribution,
} from './extension-types';
export { slots } from './extension-types';
export { ExtensionRegistry, extensions };

const ExtensionContext = createContext(extensions);

export function ExtensionsProvider({
  registry = extensions,
  children,
}: {
  registry?: ExtensionRegistry;
  children: ReactNode;
}) {
  return <ExtensionContext.Provider value={registry}>{children}</ExtensionContext.Provider>;
}

export function useExtensions(): ExtensionRegistry {
  return useContext(ExtensionContext);
}

/** An empty slot adds no wrapper. Permission checks happen before lazy imports. */
export function Slot<K extends keyof ExtensionSlots>({
  name,
  props,
}: {
  name: K;
  props: ExtensionSlots[K];
}) {
  const registry = useExtensions();
  const permissions = usePage().props.auth?.permissions ?? [];
  return registry.getSlot(name).map(({ id, permission, component: Component, fallback }) =>
    !permission || permissions.includes(permission) ? (
      <Suspense key={id} fallback={fallback ?? null}>
        <Component {...props} />
      </Suspense>
    ) : null,
  );
}
