import type { ComponentProps, ComponentType, ReactNode } from 'react';
import type { AppTopbar } from './components/AppTopbar';
import type { SidebarUserMenu } from './layouts/SidebarUserMenu';

export const slots = {
  usersEditPanels: 'users.edit.panels',
  tenantsSettingsSections: 'tenants.settings.sections',
} as const;

/** Hosts/modules may augment this interface to declare further typed slots. */
export interface ExtensionSlots {
  'users.edit.panels': { userId: string };
  'tenants.settings.sections': { tenant: { id: string; name: string; slug: string } };
}

export interface SlotContribution<P> {
  /** Unique within the slot; prefix with your module's package name. */
  id: string;
  order?: number;
  permission?: string;
  component: ComponentType<P>;
  /** Reserve the panel's space while a lazy component loads. */
  fallback?: ReactNode;
}

export interface LayoutComponents {
  UserMenu: ComponentType<ComponentProps<typeof SidebarUserMenu>>;
  Topbar: ComponentType<ComponentProps<typeof AppTopbar>>;
}

export type FieldType = 'bool' | 'int' | 'float' | 'string' | 'json';

/** Settings editor metadata shared with custom renderers. */
export interface SettingsFieldMeta {
  name: string;
  type: FieldType;
  value: unknown;
  default: unknown;
  description: string;
  is_secret: boolean;
  requires_restart: boolean;
  group: string | null;
  env_var: string;
  /** The field's SM_* env var is present in the process environment. */
  env_set?: boolean;
  /** The declaring settings class reads env at all (declares an `env_prefix`). */
  env_readable?: boolean;
  /** A stored setting overrides this field. */
  db_override?: boolean;
  /** Where the live value came from. Mirrors hydrate_settings' precedence. */
  source?: 'db' | 'env' | 'default';
  /** Closed set of accepted values, or null when the field is free text. */
  choices?: string[] | null;
  /** Editor control: `type` with an `X | None` unwrapped to `X`. */
  input_type?: FieldType;
  /** `null` is a valid value; an empty input sends it. */
  nullable?: boolean;
  /** Optional registered renderer name; unknown hints use built-in controls. */
  control?: string | null;
}

export interface SettingsFieldRendererProps {
  field: SettingsFieldMeta;
  onChange: (name: string, value: unknown) => void;
  value: unknown;
  id?: string;
}

export type MenuIcon = ComponentType<{
  className?: string;
  'aria-hidden'?: boolean | 'true' | 'false';
  strokeWidth?: number;
}>;
