import { readParked, writeParked } from "./recoveryDisposition";
import { RecoveryParkControls } from "./RecoveryParkControls";
import { useEffect, useRef, useState } from "react";
import { api, ApiError, lookupPreparation, segment } from "./api";
import { ErrorMessage } from "./components";
import type { Translate } from "./i18n";
import type { Task, Workspace } from "./types";

const uuid =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
export const AUTO_CHECK_LIMIT = 3;
export interface DraftPreparePayload {
  operation: "paper-abstract-draft";
  mode: "connected";
  instructions: string;
  source_selection: {
    artifact_id: string;
    source_record_id: string;
    start: number;
    end: number;
  };
}
interface Identity {
  version: 1;
  workspace_instance_id: string;
  project_id: string;
  key: string;
  state: "pending";
}
export interface RecoveryEntry extends Identity {
  parked?: boolean;
  parkStorageFailed?: boolean;
  parkSessionOnly?: boolean;
  phase:
    | "pending"
    | "sending"
    | "checking"
    | "not_observed"
    | "error"
    | "conflict"
    | "unsent"
    | "found";
  task?: Task;
  scopeSettled?: boolean;
  error?: unknown;
}
export interface PreparationRecovery {
  supported: boolean;
  blocked: boolean;
  park: (key: string, sessionOnly?: boolean) => boolean;
  storageUnavailable: boolean;
  retryError?: unknown;
  entries: RecoveryEntry[];
  prepare: (
    payload: DraftPreparePayload,
  ) => Promise<{ key: string; task?: Task }>;
  check: (key: string) => Promise<Task | undefined>;
  retry: (key: string) => Promise<void>;
  canRetry: (key: string) => boolean;
  dismiss: (key: string) => void;
  canDismiss: (key: string) => boolean;
}
export function preparationPrefix(
  origin: string,
  namespace: string,
  projectId: string,
): string {
  return `research-hub:prepare:v1:${encodeURIComponent(origin)}:${namespace}:${encodeURIComponent(projectId)}:`;
}
function pendingIdentity(
  value: unknown,
  namespace: string,
  projectId: string,
): value is Identity {
  if (!value || typeof value !== "object") return false;
  const data = value as Identity;
  return (
    Object.keys(data).sort().join() ===
      "key,project_id,state,version,workspace_instance_id" &&
    data.version === 1 &&
    data.workspace_instance_id === namespace &&
    data.project_id === projectId &&
    data.state === "pending" &&
    typeof data.key === "string" &&
    uuid.test(data.key)
  );
}
function knownRejection(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    [
      "source_selection_required",
      "invalid_source",
      "stale_input",
      "unsafe_path",
      "context_limit",
      "unsupported_source",
      "adapter_changed",
      "unsupported_capability",
    ].includes(error.code)
  );
}

/** Only this abstract Prepare contract is recoverable. No generic mutation replay. */
export function usePreparationRecovery(
  projectId: string,
  capability: Workspace["capabilities"]["prepare_reconciliation"],
  tasks: Task[],
  onFound: (task: Task) => Promise<void>,
): PreparationRecovery {
  const namespace =
    capability?.version === 1 &&
    typeof capability.workspace_instance_id === "string" &&
    uuid.test(capability.workspace_instance_id)
      ? capability.workspace_instance_id
      : "";
  const scope = namespace
    ? preparationPrefix(window.location.origin, namespace, projectId)
    : "";
  const [entries, setEntries] = useState<RecoveryEntry[]>([]);
  const [storageUnavailable, setStorageUnavailable] = useState(false);
  const [retryError, setRetryError] = useState<unknown>();
  const records = useRef(new Map<string, RecoveryEntry>());
  const payloads = useRef(new Map<string, DraftPreparePayload>());
  const locks = useRef(new Set<string>());
  const controllers = useRef(new Set<AbortController>());
  const active = useRef(scope);
  active.current = scope;
  const mounted = useRef(true);
  const foundCallback = useRef(onFound);
  foundCallback.current = onFound;
  const current = () => mounted.current && active.current === scope;
  const publish = () => {
    if (current()) setEntries([...records.current.values()]);
  };
  function save(entry: Identity): boolean {
    try {
      window.localStorage.setItem(scope + entry.key, JSON.stringify(entry));
      return true;
    } catch {
      if (current()) setStorageUnavailable(true);
      return false;
    }
  }
  function removeStored(key: string) {
    try {
      window.localStorage.removeItem(scope + key);
    } catch {
      if (current()) setStorageUnavailable(true);
    }
  }
  function validTask(task: unknown): task is Task {
    return (
      !!task &&
      typeof task === "object" &&
      typeof (task as Task).id === "string" &&
      Boolean((task as Task).id) &&
      (task as Task).project_id === projectId &&
      (task as Task).operation === "paper-abstract-draft"
    );
  }
  async function found(key: string, task: Task) {
    if (!current()) return;
    const entry = records.current.get(key);
    if (!entry) return;
    records.current.set(key, {
      ...entry,
      phase: "found",
      task,
      error: undefined,
    });
    publish();
    try {
      await foundCallback.current(task);
      if (current()) {
        const latest = records.current.get(key);
        if (latest?.phase === "found") {
          records.current.set(key, { ...latest, scopeSettled: true });
          publish();
        }
      }
    } catch (error) {
      if (current()) {
        records.current.set(key, {
          ...entry,
          phase: "found",
          task,
          error,
          scopeSettled: true,
        });
        publish();
      }
    }
  }
  async function check(key: string): Promise<Task | undefined> {
    const entry = records.current.get(key);
    if (
      !scope ||
      !entry ||
      locks.current.has(key) ||
      !current() ||
      (entry.phase === "conflict" && !entry.parked)
    )
      return;
    locks.current.add(key);
    const controller = new AbortController();
    controllers.current.add(controller);
    records.current.set(key, { ...entry, phase: "checking", error: undefined });
    publish();
    try {
      const value = await lookupPreparation<{
        ok: true;
        preparation: { key: string; state: string };
        task?: Task;
        scopeSettled?: boolean;
      }>(projectId, key, namespace, controller.signal);
      if (!current() || controller.signal.aborted) return;
      if (
        value.preparation?.key !== key ||
        !["found", "not_observed"].includes(value.preparation?.state)
      )
        throw new ApiError(
          "Invalid preparation lookup response",
          "invalid_response",
          200,
        );
      if (value.preparation.state === "found") {
        if (!validTask(value.task))
          throw new ApiError(
            "Invalid preparation task identity",
            "invalid_response",
            200,
          );
        await found(key, value.task);
        return value.task;
      }
      if (value.task !== undefined)
        throw new ApiError(
          "Inconsistent preparation lookup response",
          "invalid_response",
          200,
        );
      records.current.set(key, {
        ...entry,
        phase: "not_observed",
        error: undefined,
      });
      publish();
    } catch (error) {
      if (current() && !controller.signal.aborted) {
        records.current.set(key, { ...entry, phase: "error", error });
        publish();
      }
    } finally {
      controllers.current.delete(controller);
      if (current()) {
        locks.current.delete(key);
        publish();
      }
    }
  }
  async function send(key: string): Promise<Task | undefined> {
    const entry = records.current.get(key),
      payload = payloads.current.get(key);
    if (
      !entry ||
      entry.parked ||
      !payload ||
      !current() ||
      locks.current.has(key) ||
      entry.phase === "found" ||
      entry.phase === "conflict"
    )
      return;
    locks.current.add(key);
    records.current.set(key, { ...entry, phase: "sending", error: undefined });
    publish();
    let needsCheck = false;
    try {
      const value = await api<{
        ok: true;
        preparation: { version: number; key: string; disposition: string };
        task: Task;
      }>(`/projects/${segment(projectId)}/tasks`, {
        ...payload,
        prepare_request: { version: 1, workspace_instance_id: namespace, key },
      });
      if (!current()) return;
      if (
        value.preparation?.version !== 1 ||
        value.preparation.key !== key ||
        !["created", "existing"].includes(value.preparation.disposition) ||
        !validTask(value.task)
      )
        throw new ApiError(
          "Invalid preparation response",
          "invalid_response",
          200,
        );
      await found(key, value.task);
      return value.task;
    } catch (error) {
      if (!current()) return;
      if (knownRejection(error)) {
        removeStored(key);
        records.current.delete(key);
        payloads.current.delete(key);
        publish();
        throw error;
      }
      const conflict =
        error instanceof ApiError &&
        ["workspace_mismatch", "request_key_conflict"].includes(error.code);
      records.current.set(key, {
        ...entry,
        phase: conflict ? "conflict" : "error",
        error,
      });
      publish();
      needsCheck = !conflict;
    } finally {
      if (current()) {
        locks.current.delete(key);
        publish();
      }
    }
    // One bounded read after an uncertain POST; never a second POST or Run.
    if (needsCheck && current()) return check(key);
  }
  function park(key: string, sessionOnly = false): boolean {
    const entry = records.current.get(key);
    if (
      !current() ||
      !scope ||
      !entry ||
      entry.parked ||
      locks.current.has(key) ||
      ["sending", "checking", "unsent", "found"].includes(entry.phase)
    )
      return false;
    if (sessionOnly && !entry.parkStorageFailed) return false;
    if (!sessionOnly) {
      try {
        const persisted = JSON.parse(
          localStorage.getItem(scope + key) ?? "null",
        );
        if (
          !pendingIdentity(persisted, namespace, projectId) ||
          persisted.key !== key
        )
          throw new Error("Pending identity not durable");
        writeParked(
          window.location.origin,
          namespace,
          projectId,
          "prepare",
          key,
        );
      } catch {
        setStorageUnavailable(true);
        records.current.set(key, { ...entry, parkStorageFailed: true });
        publish();
        return false;
      }
    }
    records.current.set(key, {
      ...entry,
      parked: true,
      parkSessionOnly: sessionOnly,
      parkStorageFailed: false,
    });
    publish();
    return true;
  }
  async function prepare(
    payload: DraftPreparePayload,
  ): Promise<{ key: string; task?: Task }> {
    if (
      !scope ||
      [...records.current.values()].some(
        (entry) => entry.phase !== "found" && !entry.parked,
      )
    )
      throw new ApiError(
        "Resolve the pending preparation first",
        "preparation_pending",
        400,
      );
    let key: string;
    try {
      key = window.crypto.randomUUID();
      if (!uuid.test(key) || records.current.has(key)) throw new Error();
    } catch {
      throw new ApiError(
        "Cryptographic request identity is unavailable; no task was sent",
        "prepare_identity_unavailable",
        400,
      );
    }
    const identity: Identity = {
      version: 1,
      workspace_instance_id: namespace,
      project_id: projectId,
      key,
      state: "pending",
    };
    payloads.current.set(key, {
      ...payload,
      source_selection: { ...payload.source_selection },
    });
    const persisted = save(identity);
    records.current.set(key, {
      ...identity,
      phase: persisted ? "pending" : "unsent",
    });
    publish();
    // Storage failure is disclosed before any write. Explicit in-session action follows.
    return { key, task: persisted ? await send(key) : undefined };
  }
  useEffect(() => {
    let cancelled = false;
    mounted.current = true;
    records.current = new Map();
    payloads.current = new Map();
    locks.current = new Set();
    setEntries([]);
    setStorageUnavailable(false);
    setRetryError(undefined);
    if (scope) {
      try {
        for (let i = 0; i < window.localStorage.length; i++) {
          const storageKey = window.localStorage.key(i);
          if (!storageKey?.startsWith(scope)) continue;
          try {
            const value = JSON.parse(
              window.localStorage.getItem(storageKey) ?? "null",
            );
            if (
              pendingIdentity(value, namespace, projectId) &&
              storageKey === scope + value.key
            ) {
              let parked = false;
              try {
                parked = readParked(
                  window.location.origin,
                  namespace,
                  projectId,
                  "prepare",
                  value.key,
                );
              } catch {
                /* no marker authority */
              }
              records.current.set(value.key, {
                ...value,
                phase: "pending",
                parked,
              });
            }
          } catch {
            /* Invalid entries are not identities; do not echo their content. */
          }
        }
      } catch {
        setStorageUnavailable(true);
      }
      publish();
      const keys = [...records.current.keys()].slice(0, AUTO_CHECK_LIMIT);
      // Defer until the effect survives StrictMode setup/cleanup; never double-read on its probe mount.
      void Promise.resolve().then(async () => {
        for (const key of keys) {
          if (cancelled || !current()) return;
          await check(key);
        }
      });
    }
    return () => {
      cancelled = true;
      mounted.current = false;
      for (const controller of controllers.current) controller.abort();
      controllers.current.clear();
    };
  }, [scope]);
  useEffect(() => {
    if (!scope) return;
    for (const entry of records.current.values())
      if (
        entry.phase === "found" &&
        entry.scopeSettled &&
        entry.task &&
        tasks.some((task) => task.id === entry.task!.id)
      )
        removeStored(entry.key);
  }, [tasks, entries, scope]);
  const visible = entries.filter(
    (entry) =>
      entry.workspace_instance_id === namespace &&
      entry.project_id === projectId,
  );
  return {
    supported: Boolean(scope),
    blocked: visible.some((entry) => entry.phase !== "found" && !entry.parked),
    storageUnavailable,
    retryError,
    entries: visible,
    park,
    prepare,
    check,
    retry: async (key) => {
      try {
        await send(key);
      } catch (error) {
        // A confirmed validation rejection retires the request; disclose it without an unhandled click promise.
        if (current()) {
          setRetryError(error);
        }
      }
    },
    canRetry: (key) =>
      !records.current.get(key)?.parked &&
      payloads.current.has(key) &&
      !locks.current.has(key) &&
      !["found", "conflict"].includes(
        records.current.get(key)?.phase ?? "found",
      ),
    canDismiss: (key) => {
      const entry = records.current.get(key);
      return (
        entry?.phase === "unsent" ||
        Boolean(
          entry?.phase === "found" &&
          entry.scopeSettled &&
          entry.task &&
          tasks.some((task) => task.id === entry.task!.id),
        )
      );
    },
    dismiss: (key) => {
      const entry = records.current.get(key);
      if (
        entry?.phase !== "unsent" &&
        (entry?.phase !== "found" ||
          !entry.scopeSettled ||
          !entry.task ||
          !tasks.some((task) => task.id === entry.task!.id))
      )
        return;
      removeStored(key);
      records.current.delete(key);
      payloads.current.delete(key);
      publish();
    },
  };
}

export function PreparationRecoveryPanel({
  recovery,
  t,
  onReview,
  onSeparate,
}: {
  recovery: PreparationRecovery;
  onSeparate?: () => void;
  t: Translate;
  onReview: (id: string) => void;
}) {
  if (!recovery.supported) return null;
  return (
    <>
      {recovery.retryError !== undefined && (
        <ErrorMessage error={recovery.retryError} t={t} />
      )}
      {recovery.storageUnavailable && (
        <p role="status">{t("prepareStorageUnavailable")}</p>
      )}
      {recovery.entries.length > 0 && (
        <section className="panel" aria-label={t("prepareRecoveryTitle")}>
          <h2>{t("prepareRecoveryTitle")}</h2>
          <p>{t("prepareRecoveryBound")}</p>
          {recovery.entries.map((entry, index) => (
            <article className="research-record" key={entry.key}>
              <h3>
                {t("preparePendingItem")} {index + 1}
              </h3>
              <p>
                {t(
                  entry.phase === "found"
                    ? "prepareFound"
                    : entry.phase === "not_observed"
                      ? "prepareNotObserved"
                      : entry.phase === "unsent"
                        ? "prepareStorageConfirm"
                        : entry.phase === "sending"
                          ? "abstractPreparingLeave"
                          : entry.phase === "checking"
                            ? "loading"
                            : "preparePendingUnknown",
                )}
              </p>
              <RecoveryParkControls
                entry={entry}
                recovery={recovery}
                t={t}
                onSeparate={onSeparate}
              />
              {entry.error !== undefined && (
                <ErrorMessage error={entry.error} t={t} />
              )}
              {entry.phase === "found" && entry.task ? (
                <>
                  <button
                    className="button secondary"
                    onClick={() => onReview(entry.task!.id)}
                  >
                    {t("prepareOpenRecovered")}
                  </button>
                  <button
                    className="button text-button"
                    disabled={!recovery.canDismiss(entry.key)}
                    onClick={() => recovery.dismiss(entry.key)}
                  >
                    {t("dismiss")}
                  </button>
                </>
              ) : (
                <>
                  <button
                    className="button secondary"
                    disabled={
                      ["sending", "checking", "conflict", "unsent"].includes(
                        entry.phase,
                      ) && !(entry.parked && entry.phase === "conflict")
                    }
                    onClick={() => void recovery.check(entry.key)}
                  >
                    {t("prepareCheck")}
                  </button>
                  {entry.phase === "unsent" && (
                    <button
                      className="button text-button"
                      onClick={() => recovery.dismiss(entry.key)}
                    >
                      {t("cancel")}
                    </button>
                  )}
                  {recovery.canRetry(entry.key) && (
                    <button
                      className="button secondary"
                      onClick={() => void recovery.retry(entry.key)}
                    >
                      {t(
                        entry.phase === "unsent"
                          ? "prepareSessionOnly"
                          : "prepareRetrySame",
                      )}
                    </button>
                  )}
                  {!recovery.canRetry(entry.key) &&
                    !["sending", "checking", "unsent", "conflict"].includes(
                      entry.phase,
                    ) && <p>{t("prepareNoPayload")}</p>}
                </>
              )}
            </article>
          ))}
        </section>
      )}
    </>
  );
}
