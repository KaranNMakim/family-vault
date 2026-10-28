export type Role = "owner" | "spouse" | "nominee" | "advisor" | "emergency";
export type Severity = "critical" | "high" | "medium" | "low" | "info";

export interface Principal {
  role: Role;
  person_id: string | null;
  advisor_id: string | null;
  spouse_scope: "full" | "shared";
  access_request_id: string | null;
}

export interface FamilyMeta {
  id: string;
  display_name: string;
  story?: string;
  owner?: string;
  primary_earner?: string;
  synthetic?: boolean;
}

export interface Session {
  token: string;
  family: FamilyMeta;
  principal: Principal;
  can_write: boolean;
  notice: string;
  security?: { two_factor: boolean; idle_timeout_minutes: number; encryption: string };
}

export interface Persona {
  role: Role;
  person_id?: string;
  advisor_id?: string;
  access_request_id?: string;
  label: string;
}

export interface Provenance {
  source: string;
  timestamp: string;
  confidence: number;
  method: "rule" | "model" | "human";
}

export interface Ref {
  id: string;
  name: string;
}

export interface GNode {
  id: string;
  cls: "Person" | "Asset" | "Liability" | "Document" | "Institution" | "Advisor";
  props: Record<string, unknown>;
  provenance: Provenance;
  hidden_fields?: string[];
}

export interface Item extends GNode {
  links?: {
    owners: (Ref & { role: string })[];
    nominees: (Ref & { minor: boolean })[];
    institution: Ref | null;
    documents: GNode[];
    advisors: Ref[];
    knows?: Ref[];
  };
  inferred?: Record<string, { value: unknown; provenance: Provenance }>;
  age?: number | null;
}

export interface GEdge {
  id: string;
  src: string;
  rel: string;
  dst: string;
  props: Record<string, unknown>;
}

export interface Graph {
  nodes: GNode[];
  edges: GEdge[];
  visible_items: string[];
  gaps_by_node: Record<string, { key: string; severity: Severity; title: string }[]>;
  as_of: string;
}

export interface Gap {
  key: string;
  rule: string;
  title: string;
  category: string;
  severity: Severity;
  subject_ids: string[];
  message: string;
  fix: string;
  fix_action: { kind: string; asset_id?: string; person_id?: string; doc_types?: string[] };
}

export interface Readiness {
  score: number;
  band: string;
  categories: { category: string; label: string; max_points: number; lost: number; earned: number; gap_keys: string[] }[];
  impacts: { key: string; points_if_fixed: number }[];
  explanation: string;
}

export interface Step {
  order: number;
  action: string;
  text: string;
  institution: string | null;
  item_ids: string[];
  required_documents: string[];
  actors: string[];
  actor_ids: string[];
  blocked: boolean;
  blocked_by: string[];
  notes: string[];
}

export interface Checklist {
  scenario: string;
  scenario_label: string;
  subject_id: string;
  subject_name: string;
  disclaimer: string;
  steps: Step[];
  blocked_count: number;
}

export interface AccessRequest {
  id: string;
  requester_id: string;
  requester_name: string;
  reason: string;
  status: "pending" | "cancelled" | "active" | "expired";
  created_at: string;
  wait_hours: number;
  available_at: string;
  expires_at: string | null;
  timeline: { ts: string; event: string; actor: string }[];
}

export interface Question {
  id: string;
  section: string;
  section_title: string;
  prompt: string;
  input: "person_form" | "yesno" | "asset_form" | "liability_form" | "done";
  skippable: boolean;
  context: {
    people?: Ref[];
    ask_relation?: boolean;
    asset_type?: string;
    default_doc_type?: string;
  };
}

export interface OnboardingResult {
  question: Question;
  progress: { done: number; total: number; percent: number; section: string; sections: { id: string; title: string; skipped: boolean }[] };
  last_created: string[];
  message: string;
}
