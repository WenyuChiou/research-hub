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
export interface Workspace {
  ok: true;
  projects: Project[];
  capabilities: {
    codex: Capability;
    writing: Capability;
    approval: Capability;
  };
  protection_scope: string;
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
