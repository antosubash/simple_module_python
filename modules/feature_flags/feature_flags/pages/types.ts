/** Shape of one row in the `flags` prop — mirrors `FeatureFlagView` in contracts/schemas.py. */
export interface FeatureFlag {
  name: string;
  description: string;
  default_enabled: boolean;
  /** The value this scope resolves to right now. */
  enabled: boolean;
  /** Whether the row that produced `enabled` lives at *this* scope. */
  overridden: boolean;
  /** The system value behind a tenant scope; null when viewing system scope. */
  system_enabled: boolean | null;
}
