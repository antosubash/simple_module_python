import type { ComponentType } from 'react';
import type {
  ExtensionSlots,
  LayoutComponents,
  MenuIcon,
  SettingsFieldRendererProps,
  SlotContribution,
} from './extension-types';

/** Configure before rendering. Each application (or test) can own its registry. */
export class ExtensionRegistry {
  private readonly contributions = new Map<keyof ExtensionSlots, unknown>();
  private readonly layouts: Partial<LayoutComponents> = {};
  private readonly icons = new Map<string, MenuIcon>();
  private readonly fieldRenderers = new Map<string, ComponentType<SettingsFieldRendererProps>>();
  private readonly registrations = new Set<string>();

  runOnce(name: string, register: () => void): void {
    if (this.registrations.has(name)) return;
    register();
    this.registrations.add(name);
  }

  registerSlot<K extends keyof ExtensionSlots>(
    name: K,
    contribution: SlotContribution<ExtensionSlots[K]>,
  ): void {
    const entries = this.getSlot(name);
    if (entries.some((entry) => entry.id === contribution.id)) {
      throw new Error(`Duplicate contribution ${contribution.id} in ${String(name)}`);
    }
    this.contributions.set(
      name,
      [...entries, contribution].sort((a, b) => (a.order ?? 0) - (b.order ?? 0)),
    );
  }

  getSlot<K extends keyof ExtensionSlots>(name: K): readonly SlotContribution<ExtensionSlots[K]>[] {
    // Each key is written only by registerSlot with that key's declared props.
    return (
      (this.contributions.get(name) as SlotContribution<ExtensionSlots[K]>[] | undefined) ?? []
    );
  }

  registerLayout<K extends keyof LayoutComponents>(name: K, component: LayoutComponents[K]): void {
    this.layouts[name] = component;
  }

  getLayouts(): Readonly<Partial<LayoutComponents>> {
    return this.layouts;
  }

  registerIcon(name: string, component: MenuIcon): void {
    if (this.icons.has(name)) throw new Error(`Duplicate menu icon ${name}`);
    this.icons.set(name, component);
  }

  getIcon(name: string): MenuIcon | undefined {
    return this.icons.get(name);
  }

  registerFieldRenderer(name: string, component: ComponentType<SettingsFieldRendererProps>): void {
    this.fieldRenderers.set(name, component);
  }

  getFieldRenderer(name: string): ComponentType<SettingsFieldRendererProps> | undefined {
    return this.fieldRenderers.get(name);
  }
}

export const extensions = new ExtensionRegistry();
