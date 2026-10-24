import { useEffect, useRef, useState } from "react";
import { api, ApiError, lookupTextIntake, segment } from "./api";
import { ErrorMessage } from "./components";
import type { Translate } from "./i18n";
import type { ProjectDetail, Workspace } from "./types";
import {
  intakeSupported,
  requestUUID,
  validSavedText,
  type IntakePayload,
  type SavedText,
} from "./textIntake";

export const INTAKE_AUTO_CHECK_LIMIT = 3;
interface Identity {
  version: 1;
  workspace_instance_id: string;
  project_id: string;
  key: string;
  state: "pending";
}
export interface IntakeEntry extends Identity {
  phase:
    | "pending"
    | "sending"
    | "checking"
    | "not_observed"
    | "error"
    | "conflict"
    | "unsent"
    | "found";
  saved?: SavedText;
  scopeSettled?: boolean;
  error?: unknown;
}
export interface TextIntakeRecovery {
  supported: boolean;
  blocked: boolean;
  storageUnavailable: boolean;
  error?: unknown;
  entries: IntakeEntry[];
  submit: (
    payload: IntakePayload,
  ) => Promise<{ key: string; saved?: SavedText }>;
  check: (key: string) => Promise<SavedText | undefined>;
  retry: (key: string) => Promise<void>;
  canRetry: (key: string) => boolean;
  canDismiss: (key: string) => boolean;
  dismiss: (key: string) => void;
}
export function intakePrefix(
  origin: string,
  namespace: string,
  project: string,
) {
  return (
    "research-hub:text-intake:v1:" +
    encodeURIComponent(origin) +
    ":" +
    namespace +
    ":" +
    encodeURIComponent(project) +
    ":"
  );
}
function isIdentity(
  value: unknown,
  namespace: string,
  project: string,
): value is Identity {
  if (!value || typeof value !== "object") return false;
  const v = value as Identity;
  return (
    Object.keys(v).sort().join() ===
      "key,project_id,state,version,workspace_instance_id" &&
    v.version === 1 &&
    v.workspace_instance_id === namespace &&
    v.project_id === project &&
    v.state === "pending" &&
    typeof v.key === "string" &&
    requestUUID.test(v.key)
  );
}
function preWriteRejection(error: unknown) {
  return (
    error instanceof ApiError &&
    [
      "invalid_source",
      "context_limit",
      "unsupported_source",
      "unsupported_capability",
    ].includes(error.code)
  );
}

/** Intake-specific correlation; never feeds its identity or retained bytes into task APIs. */
export function useTextIntakeRecovery(
  projectId: string,
  capability: Workspace["capabilities"]["text_intake"],
  detail: ProjectDetail,
  onFound: (saved: SavedText) => Promise<void>,
): TextIntakeRecovery {
  const namespace = intakeSupported(capability)
    ? capability!.workspace_instance_id
    : "";
  const scope = namespace
    ? intakePrefix(window.location.origin, namespace, projectId)
    : "";
  const [entries, setEntries] = useState<IntakeEntry[]>([]),
    [storageUnavailable, setStorageUnavailable] = useState(false),
    [error, setError] = useState<unknown>();
  const records = useRef(new Map<string, IntakeEntry>()),
    payloads = useRef(new Map<string, IntakePayload>()),
    locks = useRef(new Set<string>()),
    controllers = useRef(new Set<AbortController>());
  const active = useRef(scope);
  active.current = scope;
  const mounted = useRef(true);
  const callback = useRef(onFound);
  callback.current = onFound;
  const current = () => mounted.current && active.current === scope;
  const publish = () => {
    if (current()) setEntries([...records.current.values()]);
  };
  function removeStored(key: string) {
    try {
      localStorage.removeItem(scope + key);
    } catch {
      if (current()) setStorageUnavailable(true);
    }
  }
  function incorporated(saved: SavedText) {
    return (
      detail.records.some((item) => item.id === saved.record.id) &&
      detail.artifacts.some((item) => item.id === saved.artifact.id)
    );
  }
  async function found(key: string, saved: SavedText) {
    if (!current()) return;
    const entry = records.current.get(key);
    if (!entry) return;
    records.current.set(key, {
      ...entry,
      phase: "found",
      saved,
      error: undefined,
    });
    publish();
    try {
      await callback.current(saved);
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
          saved,
          scopeSettled: true,
          error,
        });
        publish();
      }
    }
  }
  async function check(key: string): Promise<SavedText | undefined> {
    const entry = records.current.get(key);
    if (
      !scope ||
      !entry ||
      locks.current.has(key) ||
      !current() ||
      entry.phase === "conflict"
    )
      return;
    locks.current.add(key);
    const controller = new AbortController();
    controllers.current.add(controller);
    records.current.set(key, { ...entry, phase: "checking", error: undefined });
    publish();
    try {
      const value = await lookupTextIntake<
        {
          ok: true;
          intake: { version: number; key: string; state: string };
        } & Partial<SavedText>
      >(projectId, key, namespace, controller.signal);
      if (!current() || controller.signal.aborted) return;
      if (
        value.intake?.version !== 1 ||
        value.intake.key !== key ||
        !["found", "not_observed"].includes(value.intake.state)
      )
        throw new ApiError(
          "Invalid text-intake lookup response",
          "invalid_response",
          200,
        );
      if (value.intake.state === "found") {
        if (!validSavedText(value, projectId, key))
          throw new ApiError(
            "Invalid saved-text linkage",
            "invalid_response",
            200,
          );
        await found(key, value);
        return value;
      }
      if (
        value.record !== undefined ||
        value.artifact !== undefined ||
        value.preview !== undefined
      )
        throw new ApiError(
          "Inconsistent text-intake lookup response",
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
  async function send(key: string): Promise<SavedText | undefined> {
    const entry = records.current.get(key),
      payload = payloads.current.get(key);
    if (
      !entry ||
      !payload ||
      !current() ||
      locks.current.has(key) ||
      ["found", "conflict"].includes(entry.phase)
    )
      return;
    locks.current.add(key);
    records.current.set(key, { ...entry, phase: "sending", error: undefined });
    publish();
    let needsCheck = false;
    try {
      const value = await api<
        {
          ok: true;
          intake: { version: number; key: string; disposition: string };
        } & SavedText
      >("/projects/" + segment(projectId) + "/source-text", {
        ...payload,
        intake_request: { version: 1, workspace_instance_id: namespace, key },
      });
      if (!current()) return;
      if (
        value.intake?.version !== 1 ||
        value.intake.key !== key ||
        !["created", "existing"].includes(value.intake.disposition) ||
        !validSavedText(value, projectId, key)
      )
        throw new ApiError(
          "Invalid saved-text response",
          "invalid_response",
          200,
        );
      await found(key, value);
      return value;
    } catch (error) {
      if (!current()) return;
      if (preWriteRejection(error)) {
        removeStored(key);
        records.current.delete(key);
        payloads.current.delete(key);
        publish();
        throw error;
      }
      const conflict =
        error instanceof ApiError &&
        [
          "workspace_mismatch",
          "request_key_conflict",
          "file_conflict",
        ].includes(error.code);
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
    // One bounded read, never automatic replay, new-key retry, Prepare or Run.
    if (needsCheck && current()) return check(key);
  }
  async function submit(
    payload: IntakePayload,
  ): Promise<{ key: string; saved?: SavedText }> {
    if (
      !scope ||
      [...records.current.values()].some((e) => e.phase !== "found")
    )
      throw new ApiError(
        "Resolve the pending text save first",
        "text_intake_pending",
        400,
      );
    let key: string;
    try {
      key = crypto.randomUUID();
      if (!requestUUID.test(key)) throw new Error();
    } catch {
      throw new ApiError(
        "Secure request identity is unavailable; no text was sent",
        "intake_identity_unavailable",
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
    payloads.current.set(key, { ...payload });
    let persisted = true;
    try {
      localStorage.setItem(scope + key, JSON.stringify(identity));
    } catch {
      persisted = false;
      setStorageUnavailable(true);
    }
    records.current.set(key, {
      ...identity,
      phase: persisted ? "pending" : "unsent",
    });
    setError(undefined);
    publish();
    return { key, saved: persisted ? await send(key) : undefined };
  }
  useEffect(() => {
    let cancelled = false;
    mounted.current = true;
    records.current = new Map();
    payloads.current = new Map();
    locks.current = new Set();
    setEntries([]);
    setStorageUnavailable(false);
    setError(undefined);
    if (scope) {
      try {
        for (let i = 0; i < localStorage.length; i++) {
          const k = localStorage.key(i);
          if (!k?.startsWith(scope)) continue;
          try {
            const v = JSON.parse(localStorage.getItem(k) ?? "null");
            if (isIdentity(v, namespace, projectId) && k === scope + v.key)
              records.current.set(v.key, { ...v, phase: "pending" });
          } catch {
            /* Never render stored arbitrary content. */
          }
        }
      } catch {
        setStorageUnavailable(true);
      }
      publish();
      const keys = [...records.current.keys()].slice(
        0,
        INTAKE_AUTO_CHECK_LIMIT,
      );
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
      for (const c of controllers.current) c.abort();
      controllers.current.clear();
    };
  }, [scope]);
  useEffect(() => {
    if (scope)
      for (const e of records.current.values())
        if (
          e.phase === "found" &&
          e.scopeSettled &&
          e.saved &&
          incorporated(e.saved)
        )
          removeStored(e.key);
  }, [detail, entries, scope]);
  const visible = entries.filter(
    (e) => e.workspace_instance_id === namespace && e.project_id === projectId,
  );
  function canDismiss(key: string) {
    const e = records.current.get(key);
    return (
      e?.phase === "unsent" ||
      Boolean(
        e?.phase === "found" &&
        e.scopeSettled &&
        e.saved &&
        incorporated(e.saved),
      )
    );
  }
  return {
    supported: Boolean(scope),
    blocked: visible.some((e) => e.phase !== "found"),
    storageUnavailable,
    error,
    entries: visible,
    submit,
    check,
    retry: async (key) => {
      try {
        await send(key);
      } catch (error) {
        if (current()) setError(error);
      }
    },
    canRetry: (key) =>
      payloads.current.has(key) &&
      !locks.current.has(key) &&
      !["found", "conflict"].includes(
        records.current.get(key)?.phase ?? "found",
      ),
    canDismiss,
    dismiss: (key) => {
      if (!canDismiss(key)) return;
      removeStored(key);
      records.current.delete(key);
      payloads.current.delete(key);
      publish();
    },
  };
}

export function TextIntakeRecoveryPanel({
  recovery,
  t,
  onOpen,
}: {
  recovery: TextIntakeRecovery;
  t: Translate;
  onOpen: (saved: SavedText) => void;
}) {
  if (!recovery.supported) return null;
  return (
    <>
      {recovery.error !== undefined && (
        <ErrorMessage error={recovery.error} t={t} />
      )}
      {recovery.storageUnavailable && (
        <p role="status">{t("intakeStorageUnavailable")}</p>
      )}
      {recovery.entries.length > 0 && (
        <section className="panel" aria-label={t("intakeRecoveryTitle")}>
          <h2>{t("intakeRecoveryTitle")}</h2>
          <p>{t("intakeRecoveryBound")}</p>
          {recovery.entries.map((entry, index) => (
            <article className="research-record" key={entry.key}>
              <h3>
                {t("intakePendingItem")} {index + 1}
              </h3>
              <p>
                {t(
                  entry.phase === "found"
                    ? "intakeFound"
                    : entry.phase === "not_observed"
                      ? "intakeNotObserved"
                      : entry.phase === "unsent"
                        ? "intakeStorageConfirm"
                        : entry.phase === "sending"
                          ? "intakeSavingLeave"
                          : entry.phase === "checking"
                            ? "loading"
                            : "intakePendingUnknown",
                )}
              </p>
              {entry.error !== undefined && (
                <ErrorMessage error={entry.error} t={t} />
              )}
              {entry.phase === "found" && entry.saved ? (
                <>
                  {entry.saved.preview_status !== "available" && (
                    <p role="status">{t("intakeSavedUnavailable")}</p>
                  )}
                  <button
                    className="button secondary"
                    onClick={() => onOpen(entry.saved!)}
                  >
                    {t("intakeOpenSaved")}
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
                    disabled={[
                      "sending",
                      "checking",
                      "conflict",
                      "unsent",
                    ].includes(entry.phase)}
                    onClick={() => void recovery.check(entry.key)}
                  >
                    {t("intakeCheck")}
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
                          ? "intakeSessionOnly"
                          : "intakeRetrySame",
                      )}
                    </button>
                  )}
                  {!recovery.canRetry(entry.key) &&
                    !["sending", "checking", "unsent", "conflict"].includes(
                      entry.phase,
                    ) && <p>{t("intakeNoPayload")}</p>}
                </>
              )}
            </article>
          ))}
        </section>
      )}
    </>
  );
}
