export interface Share {
  id: string;
  resource_type: string;
  resource_id: string;
  subject_type: string;
  subject_id: string;
  subject_label: string | null;
  role: string;
  granted_by: string;
  granted_by_label: string | null;
  expires_at: string | null;
  expired: boolean;
  created_at: string | null;
}
