/** Shapes shared by the raw-store screens and their sub-components. */

export type SettingScope = 'system' | 'tenant' | 'user';

export type ValueType = 'string' | 'bool' | 'int' | 'float' | 'json';

export const VALUE_TYPES: readonly ValueType[] = ['string', 'bool', 'int', 'float', 'json'];

export const SCOPES: readonly SettingScope[] = ['system', 'tenant', 'user'];

export interface Setting {
  id: number;
  scope: SettingScope;
  scope_id: string;
  key: string;
  value: string;
  value_type: ValueType;
  description: string | null;
}

export interface Pagination {
  page: number;
  per_page: number;
  total: number;
}
