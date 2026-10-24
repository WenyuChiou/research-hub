export type Locale = "en" | "zh-TW";
export type Page =
  | "overview"
  | "literature"
  | "evidence"
  | "design"
  | "manuscript"
  | "review";
export type Operation =
  | "frame"
  | "outline"
  | "draft"
  | "review"
  | "revise"
  | "rebuttal"
  | "synthesize"
  | "audit";
export interface Project {
  id: string;
  title: string;
  archetype: "empirical" | "review";
  goal: string;
  created_at?: string;
}
export interface Capability {
  status: string;
  message: string;
}
export interface SetupSnapshot {
  schema_version: number;
  source: string;
  current_status: "unknown";
  freshness: "missing" | "invalid" | "clock_skew" | "stale" | "saved";
  observed_at: string | null;
  age_seconds: number | null;
  display_max_age_seconds: number;
  components: Record<string, string>;
}
export interface Workspace {
  ok: true;
  projects: Project[];
  capabilities: {
    codex: Capability;
    writing: Capability;
    approval: Capability;
  };
  protection_scope: string;
  setup_snapshot?: SetupSnapshot;
}
export interface ResearchRecord {
  id: string;
  kind: string;
  data: Record<string, unknown>;
}
export interface Artifact {
  id: string;
  path: string;
  role: string;
  sha256: string;
  current: boolean;
}
export interface Task {
  id: string;
  operation: Operation;
  mode: "handoff" | "connected";
  status: string;
  action_hash: string;
  result?: unknown;
  error?: string;
  blocker?: string;
  execution_provenance?: Record<string, unknown> | null;
  updated_at?: string;
  acceptance_current?: boolean;
  freshness?: TaskFreshness;
}
export type RevisionStatus = "current" | "stale" | "unknown";
export interface TaskFreshness {
  status: RevisionStatus;
  reasons: { code: string; message: string; ref: string; detail?: string }[];
  input_references: RevisionReference[];
  output_references: RevisionReference[];
}
export interface RevisionReference {
  kind: string;
  ref: string;
  status: RevisionStatus;
  path?: string;
  expected_sha256?: string;
  observed_sha256?: string;
}
export interface DeliveryAction {
  id: string;
  kind: "delivery_bundle";
  status:
    | "awaiting_human"
    | "approved"
    | "pending_external_action"
    | "completed"
    | "declined"
    | "cancelled";
  action_hash: string;
  packet: unknown;
  receipt?: { path: string; sha256: string; verified_at: string };
}
export interface ProjectDetail {
  ok: true;
  project: Project;
  artifacts: Artifact[];
  records: ResearchRecord[];
  tasks: Task[];
  actions: DeliveryAction[];
  manuscript: Record<string, unknown> | null;
  workflow: Record<string, unknown> | null;
  warnings: string[];
}
export interface SearchResult {
  source_id: string;
  title: string;
  locator?: string;
  doi?: string;
}
