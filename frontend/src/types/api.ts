// Types mirroring backend/app/api/v1/schemas.py and contracts/openapi.yaml.

export type DocumentType =
  | "CALL_REPORT"
  | "CLIENT_PROFILE"
  | "CREDIT_MEMO_NARRATIVE"
  | "KYC_SUMMARY";

export type DocumentStatus = "DRAFT" | "UNDER_REVIEW" | "REJECTED" | "APPROVED";

/** Never set to CLEARED by the system — Shariah review happens outside it. */
export type ShariahStatus = "PENDING_REVIEW" | "CLEARED" | "FLAGGED";

export type Confidence = "HIGH" | "MEDIUM" | "LOW";

export type UserRole = "RM" | "TEAM_LEAD" | "COMPLIANCE" | "SHARIAH_REVIEWER";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  team_id: string | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface ClientSummary {
  id: string;
  client_reference: string;
  legal_name: string;
  trade_name: string | null;
  sector: string;
  relationship_since: string | null;
  kyc_status: string;
  is_synthetic: true;
}

export interface SourceOption {
  source_id: string;
  source_type: "CLIENT_RECORD" | "UPLOADED_DOCUMENT";
  source_system: string | null;
  label: string;
  effective_date: string | null;
  is_external: boolean;
}

export interface SourceConflict {
  field: string;
  values: Array<{ source_id: string; source_system: string; value: unknown }>;
}

export interface AssembledContext {
  client_id: string;
  client_reference: string;
  document_type: DocumentType;
  required_inputs: string[];
  sources: SourceOption[];
  conflicts: SourceConflict[];
}

/** A first-class output state, not an error. Blocks approval until resolved. */
export interface Gap {
  field: string;
  label: string;
  resolved: boolean;
  resolution_note: string | null;
}

export interface Section {
  section_key: string;
  title: string;
  ordinal: number;
  content: string | null;
  evidence_refs: string[];
  gaps: Gap[];
  confidence: Confidence;
  is_rm_edited: boolean;
  contains_external_data: boolean;
}

export interface ScreeningFinding {
  term: string;
  section_key: string;
  severity: string;
  rule_id: string;
  rationale?: string;
}

export interface DocumentDetail {
  id: string;
  client_id: string;
  client_reference: string;
  document_type: DocumentType;
  status: DocumentStatus;
  shariah_status: ShariahStatus;
  created_by: string;
  created_at: string;
  version_number: number;
  content_hash: string;
  ai_generated: true;
  template_version: string;
  prompt_version: string;
  model_id: string | null;
  sections: Section[];
  unresolved_gap_count: number;
  screening: {
    outcome: string;
    vocabulary_version: string;
    findings: ScreeningFinding[];
  } | null;
}

export interface Evidence {
  claim_id: string;
  claim_text: string;
  source_type: string;
  source_id: string | null;
  source_label: string;
  locator: { page_start?: number; page_end?: number; char_start?: number; char_end?: number };
  verbatim_excerpt: string;
  is_external: boolean;
}

export interface ApprovalRecord {
  id: string;
  document_id: string;
  version_id: string;
  approved_by: string;
  approver_name: string;
  approver_role: string;
  content_hash: string;
  shariah_status_at_approval: ShariahStatus;
  gaps_acknowledged: Array<{ section_key: string; field: string; note: string }>;
  approved_at: string;
}

export interface ApiError {
  code: string;
  message: string;
  detail?: Record<string, unknown>;
}
