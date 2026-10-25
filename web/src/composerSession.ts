import type { TextPreview } from "./AbstractDraft";
import type { Workspace } from "./types";

export interface ComposerSnapshot {
  artifactId: string;
  preview: TextPreview | null;
  range: { start: number; end: number } | null;
  instructions: string;
  creating: boolean;
  preparationUncertain: boolean;
  preparedTaskId: string | null;
  preparationKey: string | null;
  operation: number;
  inputInvalidated: boolean;
}
export const MAX_COMPOSER_SESSIONS = 32;
export function emptyComposer(): ComposerSnapshot {
  return {
    artifactId: "",
    preview: null,
    range: null,
    instructions: "",
    creating: false,
    preparationUncertain: false,
    preparedTaskId: null,
    preparationKey: null,
    operation: 0,
    inputInvalidated: false,
  };
}
/** App-lifetime only. Never serializes private text or evicts an unresolved operation. */
export class ComposerSession {
  private value: ComposerSnapshot;
  private listeners = new Set<() => void>();
  constructor(initial: ComposerSnapshot) {
    this.value = {
      ...initial,
      instructions:
        initial.instructions.length <= 20000 ? initial.instructions : "",
      preview:
        initial.preview &&
        new TextEncoder().encode(initial.preview.text).length <= 40000
          ? initial.preview
          : null,
    };
  }
  get = () => this.value;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  update(patch: Partial<ComposerSnapshot>, operation?: number) {
    if (operation !== undefined && operation !== this.value.operation)
      return false;
    if (patch.instructions !== undefined && patch.instructions.length > 20000)
      return false;
    if (
      patch.preview &&
      new TextEncoder().encode(patch.preview.text).length > 40000
    )
      return false;
    this.value = { ...this.value, ...patch };
    this.listeners.forEach((listener) => listener());
    return true;
  }
}
export class ComposerSessions {
  private entries = new Map<string, ComposerSession>();
  private previousNamespace: string | undefined;
  private legacyEpoch = 0;
  scope(workspace: Workspace): string {
    const caps = [
      workspace.capabilities.prepare_reconciliation,
      workspace.capabilities.text_intake,
    ].filter(Boolean);
    const ids = caps.map((cap) =>
      cap?.version === 1 &&
      typeof cap.workspace_instance_id === "string" &&
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(
        cap.workspace_instance_id,
      )
        ? cap.workspace_instance_id
        : null,
    );
    // Malformed/contradictory advertised identities cannot alias a prior legacy workspace.
    const namespace = ids.length
      ? ids.every((id) => id && id === ids[0])
        ? `instance:${ids[0]}`
        : "invalid"
      : "legacy";
    if (namespace !== this.previousNamespace) {
      this.legacyEpoch++;
      this.previousNamespace = namespace;
    }
    return namespace === "legacy" || namespace === "invalid"
      ? `${namespace}:${this.legacyEpoch}`
      : namespace;
  }
  has(key: string) {
    return this.entries.has(key);
  }
  acquire(key: string, initial: ComposerSnapshot): ComposerSession | null {
    const existing = this.entries.get(key);
    if (existing) return existing;
    if (this.entries.size >= MAX_COMPOSER_SESSIONS) return null;
    const entry = new ComposerSession(initial);
    this.entries.set(key, entry);
    return entry;
  }
  /** Only the recovery controller may settle a positively identified request. */
  settlePreparation(
    scope: string,
    projectId: string,
    preparationKey: string,
    taskId?: string,
  ) {
    const prefix = JSON.stringify([scope, projectId]).slice(0, -1) + ",";
    for (const [key, entry] of this.entries) {
      const state = entry.get();
      if (!key.startsWith(prefix) || state.preparationKey !== preparationKey)
        continue;
      if (taskId)
        entry.update({
          preparedTaskId: taskId,
          preparationUncertain: false,
          creating: false,
        });
      else if (!state.preparedTaskId)
        entry.update({ preparationKey: null, preparationUncertain: false });
    }
  }
  discard(key: string): boolean {
    const entry = this.entries.get(key);
    if (!entry) return true;
    const state = entry.get();
    if (
      state.creating ||
      state.preparationUncertain ||
      state.preparedTaskId ||
      state.preparationKey
    )
      return false;
    entry.update({ ...emptyComposer(), operation: state.operation + 1 });
    this.entries.delete(key);
    return true;
  }
}
