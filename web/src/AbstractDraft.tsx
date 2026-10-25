import { useEffect, useId, useRef, useState } from "react";
import { api, ApiError, segment } from "./api";
import { ErrorMessage, ReadText, SourceLink } from "./components";
import type { Translate } from "./i18n";
import type {
  DraftPreparePayload,
  PreparationRecovery,
} from "./PrepareRecovery";
import type { Artifact, Capability, ResearchRecord, Task } from "./types";

export function uncertainMutation(error: unknown): boolean {
  return (
    !(error instanceof ApiError) ||
    error.code === "invalid_response" ||
    error.status >= 500 ||
    error.status === 408
  );
}

export interface TextPreview {
  artifact_id: string;
  path: string;
  sha256: string;
  text: string;
  codepoint_length: number;
  bytes_read: number;
  truncated: false;
}

/** Textarea values normalize CR/CRLF and index UTF-16; server hashes/indexes raw Unicode text. */
export function originalRange(
  text: string,
  start: number,
  end: number,
): { start: number; end: number } | null {
  if (
    !Number.isInteger(start) ||
    !Number.isInteger(end) ||
    start < 0 ||
    end <= start
  )
    return null;
  const points = Array.from(text);
  const boundaries = new Map<number, number>([[0, 0]]);
  let displayed = 0;
  for (let i = 0; i < points.length; i++) {
    const point = points[i];
    if (point === "\r" && points[i + 1] === "\n") i++;
    displayed += point === "\r" ? 1 : point.length;
    boundaries.set(displayed, i + 1);
  }
  const rawStart = boundaries.get(start),
    rawEnd = boundaries.get(end);
  return rawStart === undefined || rawEnd === undefined
    ? null
    : { start: rawStart, end: rawEnd };
}

export function AbstractDraftComposer({
  projectId,
  source,
  artifacts,
  artifactLabels,
  capability,
  t,
  onPrepared,
  onCancel,
  onReview,
  recovery,
  initialArtifactId,
  initialPreview,
  restoreVersion,
  separateIntentVersion,
}: {
  projectId: string;
  source: ResearchRecord;
  artifacts: Artifact[];
  artifactLabels?: Record<string, string>;
  capability: Capability;
  t: Translate;
  onPrepared: (task: Task) => Promise<void>;
  onCancel: () => void;
  onReview?: (taskId?: string) => void;
  recovery?: PreparationRecovery;
  initialArtifactId?: string;
  initialPreview?: TextPreview;
  restoreVersion?: number;
  separateIntentVersion?: number;
}) {
  const id = useId();
  const [artifactId, setArtifactId] = useState(initialArtifactId ?? "");
  const [preview, setPreview] = useState<TextPreview | null>(
    initialPreview ?? null,
  );
  const [range, setRange] = useState<{ start: number; end: number } | null>(
    null,
  );
  const [instructions, setInstructions] = useState("");
  const [reading, setReading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [preparationUncertain, setPreparationUncertain] = useState(false);
  const [preparedTaskId, setPreparedTaskId] = useState<string | null>(null);
  const [preparationKey, setPreparationKey] = useState<string | null>(null);
  useEffect(() => {
    const recovered = recovery?.entries.find(
      (entry) => entry.key === preparationKey && entry.phase === "found",
    )?.task;
    if (recovered) {
      setPreparedTaskId(recovered.id);
      setPreparationUncertain(false);
    }
  }, [recovery?.entries, preparationKey]);
  const [error, setError] = useState<unknown>(null);
  const [restoreBlocked, setRestoreBlocked] = useState(false);
  const lastRestore = useRef(restoreVersion);
  const readController = useRef<AbortController | null>(null);
  const creationLock = useRef(false);
  const alive = useRef(true);
  const navigationVersion = useRef(0);
  useEffect(() => {
    alive.current = true;
    const changed = () => {
      navigationVersion.current += 1;
    };
    window.addEventListener("hashchange", changed);
    return () => {
      alive.current = false;
      readController.current?.abort();
      window.removeEventListener("hashchange", changed);
    };
  }, []);
  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (
        !cancelled &&
        initialArtifactId &&
        !initialPreview &&
        artifacts.some((a) => a.id === initialArtifactId && a.current)
      )
        void read();
    });
    return () => {
      cancelled = true;
    };
  }, []);
  const lastSeparate = useRef(separateIntentVersion);
  useEffect(() => {
    if (lastSeparate.current === separateIntentVersion) return;
    lastSeparate.current = separateIntentVersion;
    const parked =
      preparationKey &&
      recovery?.entries.some(
        (entry) => entry.key === preparationKey && entry.parked,
      );
    if (
      creating ||
      creationLock.current ||
      recovery?.blocked ||
      (preparationUncertain && !parked) ||
      (preparedTaskId && !parked)
    ) {
      setRestoreBlocked(true);
      return;
    }
    // Explicit new intent only; never reset an unrelated or keyless unknown request.
    readController.current?.abort();
    setReading(false);
    setRange(null);
    setInstructions("");
    setPreparationKey(null);
    setPreparationUncertain(false);
    setPreparedTaskId(null);
    setError(null);
    setRestoreBlocked(false);
  }, [separateIntentVersion]);
  const inputLocked =
    creating ||
    preparationUncertain ||
    Boolean(preparedTaskId) ||
    Boolean(
      preparationKey &&
      recovery?.entries.some(
        (entry) => entry.key === preparationKey && entry.parked,
      ),
    ) ||
    Boolean(recovery?.blocked);
  useEffect(() => {
    if (restoreVersion === lastRestore.current) return;
    lastRestore.current = restoreVersion;
    if (inputLocked || creationLock.current) {
      setRestoreBlocked(true);
      return;
    }
    if (!initialArtifactId) {
      if (source.data.intake) setRestoreBlocked(true);
      return;
    }
    readController.current?.abort();
    setArtifactId(initialArtifactId);
    setPreview(initialPreview ?? null);
    setRange(null);
    setReading(false);
    setError(null);
    setRestoreBlocked(false);
    if (
      !initialPreview &&
      artifacts.some((item) => item.id === initialArtifactId && item.current)
    )
      void read(initialArtifactId);
  }, [restoreVersion]);
  const choices = artifacts.filter(
    (item) => item.role === "evidence" && /\.(md|txt)$/i.test(item.path),
  );
  const selectedText =
    preview && range
      ? Array.from(preview.text).slice(range.start, range.end).join("")
      : "";
  function clearSelection(next: string) {
    readController.current?.abort();
    setArtifactId(next);
    setPreview(null);
    setRange(null);
    setReading(false);
    setError(null);
  }
  async function read(targetArtifactId = artifactId) {
    readController.current?.abort();
    const controller = new AbortController();
    readController.current = controller;
    setReading(true);
    setError(null);
    setPreview(null);
    setRange(null);
    try {
      const value = await api<{ ok: true; preview: TextPreview }>(
        `/projects/${segment(projectId)}/artifacts/${segment(targetArtifactId)}/text`,
        undefined,
        controller.signal,
      );
      if (!controller.signal.aborted && alive.current) {
        if (
          value.preview.artifact_id !== targetArtifactId ||
          value.preview.truncated !== false ||
          typeof value.preview.text !== "string"
        )
          throw new Error(t("abstractPreviewInvalid"));
        setPreview(value.preview);
      }
    } catch (failure) {
      if (!controller.signal.aborted && alive.current) setError(failure);
    } finally {
      if (!controller.signal.aborted && alive.current) setReading(false);
    }
  }
  async function prepare() {
    if (
      creationLock.current ||
      inputLocked ||
      !preview ||
      !range ||
      !selectedText.trim()
    )
      return;
    creationLock.current = true;
    const startedNavigation = navigationVersion.current;
    const startedHash = window.location.hash;
    setCreating(true);
    setError(null);
    try {
      const payload: DraftPreparePayload = {
        operation: "paper-abstract-draft",
        mode: "connected",
        instructions,
        source_selection: {
          artifact_id: preview.artifact_id,
          source_record_id: source.id,
          start: range.start,
          end: range.end,
        },
      };
      let task: Task | undefined;
      if (recovery?.supported) {
        const result = await recovery.prepare(payload);
        if (alive.current) setPreparationKey(result.key);
        task = result.task;
        if (!task) return; // Pending identity is kept by the project recovery controller.
      } else {
        const result = await api<{ ok: true; task: Task }>(
          `/projects/${segment(projectId)}/tasks`,
          payload,
        );
        task = result.task;
      }
      const value = { task };
      if (!value.task || typeof value.task.id !== "string" || !value.task.id)
        throw new ApiError(
          t("abstractPrepareUncertain"),
          "invalid_response",
          200,
        );
      if (alive.current) {
        setPreparedTaskId(value.task.id);
        if (!recovery?.supported) await onPrepared(value.task);
        // Hidden pages stay mounted. A late save must not override newer page
        // intent, including a hash change whose event has not fired yet.
        if (
          alive.current &&
          navigationVersion.current === startedNavigation &&
          window.location.hash === startedHash
        )
          onReview?.(value.task.id);
      }
    } catch (failure) {
      if (alive.current) {
        setError(failure);
        if (uncertainMutation(failure)) setPreparationUncertain(true);
      }
    } finally {
      creationLock.current = false;
      if (alive.current) setCreating(false);
    }
  }
  return (
    <section className="panel" aria-labelledby={`${id}-heading`}>
      <h2 id={`${id}-heading`}>{t("paper-abstract-draft")}</h2>
      <h3>{String(source.data.title ?? "")}</h3>
      <SourceLink locator={source.data.locator} />
      <p>{t("abstractIdentity")}</p>
      <p>{t("abstractScope")}</p>
      {!recovery?.supported && <p>{t("prepareLegacyFallback")}</p>}
      {recovery?.blocked && <p role="status">{t("prepareResolveFirst")}</p>}
      {choices.length === 0 ? (
        <p role="status">{t("abstractNoText")}</p>
      ) : (
        <>
          <div className="field">
            <label htmlFor={`${id}-file`}>{t("abstractChooseFile")}</label>
            <select
              id={`${id}-file`}
              value={artifactId}
              disabled={inputLocked}
              onChange={(event) => clearSelection(event.target.value)}
            >
              <option value="">{t("abstractChooseFilePlaceholder")}</option>
              {choices.map((item) => (
                <option key={item.id} value={item.id} disabled={!item.current}>
                  {artifactLabels?.[item.id] ??
                    `${t("sourceUnverifiedFile")} — ${item.path}`}
                  {!item.current ? ` — ${t("changed")}` : ""}
                </option>
              ))}
            </select>
          </div>
          <button
            className="button secondary"
            disabled={!artifactId || reading || inputLocked}
            onClick={() => void read()}
          >
            {reading ? t("loading") : t("abstractReadText")}
          </button>
        </>
      )}
      {creating && <p role="status">{t("abstractPreparingLeave")}</p>}
      {restoreBlocked && <p role="status">{t("abstractRestoreBlocked")}</p>}
      {error !== null && <ErrorMessage error={error} t={t} />}
      {preparationUncertain && !preparedTaskId && (
        <p role="status">{t("abstractPrepareUncertain")}</p>
      )}
      {preparedTaskId && <p role="status">{t("abstractPreparedKnown")}</p>}
      {(preparationUncertain || preparedTaskId) && onReview && (
        <button
          className="button secondary"
          onClick={() => onReview(preparedTaskId ?? undefined)}
        >
          {t(
            preparedTaskId ? "abstractOpenPrepared" : "abstractReviewExisting",
          )}
        </button>
      )}
      {preview && (
        <>
          <p className="file-path">{preview.path}</p>
          <p>{t("abstractSelectHelp")}</p>
          <div className="field field-wide">
            <label htmlFor={`${id}-text`}>{t("abstractText")}</label>
            <textarea
              id={`${id}-text`}
              rows={12}
              readOnly
              value={preview.text.replace(/\r\n?/g, "\n")}
              disabled={inputLocked}
              onSelect={(event) => {
                setRange(
                  originalRange(
                    preview.text,
                    event.currentTarget.selectionStart,
                    event.currentTarget.selectionEnd,
                  ),
                );
              }}
            />
          </div>
          <button
            className="button secondary"
            disabled={inputLocked}
            onClick={() =>
              setRange({ start: 0, end: Array.from(preview.text).length })
            }
          >
            {t("abstractSelectEntire")}
          </button>
          <h3>{t("abstractSelected")}</h3>
          {selectedText ? (
            <ReadText value={selectedText} />
          ) : (
            <p>{t("abstractNothingSelected")}</p>
          )}
          <p>{t("abstractDeclare")}</p>
          <div className="field field-wide">
            <label htmlFor={`${id}-instructions`}>{t("abstractPurpose")}</label>
            <textarea
              id={`${id}-instructions`}
              value={instructions}
              disabled={inputLocked}
              maxLength={20000}
              onChange={(event) => setInstructions(event.target.value)}
            />
          </div>
          <p>{t("abstractPrepareNote")}</p>
          <p>
            {t("abstractRunner")}: {capability.status}.{" "}
            {t("abstractCostUnknown")}
          </p>
          <button
            className="button primary"
            disabled={inputLocked || !selectedText.trim()}
            onClick={() => void prepare()}
          >
            {creating ? t("preparing") : t("abstractPrepare")}
          </button>
        </>
      )}
      <button
        className="button secondary"
        disabled={creating}
        onClick={onCancel}
      >
        {t("cancel")}
      </button>
    </section>
  );
}

export function AbstractDraftReview({
  task,
  t,
  onReturnToSource,
}: {
  task: Task;
  t: Translate;
  onReturnToSource?: (id: string) => void;
}) {
  const source = task.request?.research_draft?.source_pack;
  const prose =
    task.result &&
    typeof task.result === "object" &&
    "prose" in task.result &&
    typeof task.result.prose === "string"
      ? task.result.prose
      : null;
  return (
    <section className="research-record">
      <h4>{t("abstractReview")}</h4>
      <p>{t("abstractScope")}</p>
      <p>{t("abstractIdentity")}</p>
      <p>{t("abstractBindingNote")}</p>
      {source ? (
        <>
          <h4>{source.source.title}</h4>
          <SourceLink locator={source.source.locator} />
          <p>{t("abstractStoredPassage")}</p>
          <ReadText value={source.text} />
          {onReturnToSource && (
            <button
              className="button secondary"
              onClick={() => onReturnToSource(source.source_record_id)}
            >
              {t("abstractReturnSource")}
            </button>
          )}
        </>
      ) : (
        <p role="status">{t("abstractMissingPassage")}</p>
      )}
      {prose ? (
        <>
          <h4>{t("abstractCandidate")}</h4>
          <ReadText value={prose} />
        </>
      ) : (
        <p>{t("abstractNoCandidate")}</p>
      )}
      <p>{t("abstractCostUnknown")}</p>
    </section>
  );
}
