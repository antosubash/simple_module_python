import { createContext, type ReactNode, useContext } from 'react';
import { AppTopbar } from '../components/AppTopbar';
import type { LayoutComponents } from '../extension-types';
import { useExtensions } from '../extensions';
import { SidebarUserMenu } from './SidebarUserMenu';

const DEFAULT_COMPONENTS: LayoutComponents = { UserMenu: SidebarUserMenu, Topbar: AppTopbar };
const LayoutContext = createContext<LayoutComponents | null>(null);

/** App-level chrome, configured through the frontend extension registry. */
export function LayoutComponentsProvider({ children }: { children: ReactNode }) {
  const registry = useExtensions();
  return (
    <LayoutContext.Provider value={{ ...DEFAULT_COMPONENTS, ...registry.getLayouts() }}>
      {children}
    </LayoutContext.Provider>
  );
}

export function useLayoutComponents(): LayoutComponents {
  const components = useContext(LayoutContext);
  const registry = useExtensions();
  return components ?? { ...DEFAULT_COMPONENTS, ...registry.getLayouts() };
}
