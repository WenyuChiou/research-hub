import { useEffect, useId, useRef, useState } from "react";
import { ApiError } from "./api";
import { ErrorMessage, ReadText } from "./components";
import type { Translate } from "./i18n";
import type { TextIntakeRecovery } from "./TextIntakeRecovery";
import {
  encodePaste,
  readTextFile,
  validUnicode,
  type EncodedText,
  type IntakePayload,
  type SavedText,
} from "./textIntake";

export function TextIntakeForm({
  recovery,
  t,
  onClose,
  onOpen,
}: {
  recovery: TextIntakeRecovery;
  t: Translate;
  onClose: () => void;
  onOpen: (saved: SavedText) => void;
}) {
  const id = useId();
  const [mode, setMode] = useState<"paste" | "file">("paste"),
    [title, setTitle] = useState(""),
    [locator, setLocator] = useState(""),
    [scope, setScope] = useState<"unknown" | "abstract">("unknown"),
    [text, setText] = useState("");
  const [file, setFile] = useState<EncodedText | null>(null),
    [filename, setFilename] = useState(""),
    [reading, setReading] = useState(false),
    [saving, setSaving] = useState(false),
    [finished, setFinished] = useState(false),
    [requestKey, setRequestKey] = useState<string>(),
    [error, setError] = useState<unknown>();
  const alive = useRef(true),
    locked = useRef(false),
    navigation = useRef(0),
    reader = useRef<AbortController | null>(null);
  useEffect(() => {
    alive.current = true;
    const changed = () => {
      navigation.current++;
    };
    window.addEventListener("hashchange", changed);
    return () => {
      alive.current = false;
      reader.current?.abort();
      window.removeEventListener("hashchange", changed);
    };
  }, []);
  useEffect(() => {
    if (
      requestKey &&
      recovery.entries.some((e) => e.key === requestKey && e.phase === "found")
    )
      setFinished(true);
  }, [recovery.entries, requestKey]);
  const disabled = saving || recovery.blocked || finished;
  function changeMode(next: "paste" | "file") {
    reader.current?.abort();
    setReading(false);
    setMode(next);
    setFile(null);
    setFilename("");
    setError(undefined);
  }
  async function chooseFile(selected?: File) {
    reader.current?.abort();
    setFile(null);
    setFilename("");
    setError(undefined);
    if (!selected) {
      setReading(false);
      return;
    }
    const controller = new AbortController();
    reader.current = controller;
    setReading(true);
    try {
      const value = await readTextFile(selected, controller.signal);
      if (alive.current && !controller.signal.aborted) {
        setFile(value);
        setFilename(selected.name);
      }
    } catch (error) {
      if (alive.current && !controller.signal.aborted) setError(error);
    } finally {
      if (alive.current && !controller.signal.aborted) setReading(false);
    }
  }
  async function save() {
    if (locked.current || disabled || reading) return;
    locked.current = true;
    setSaving(true);
    setError(undefined);
    const startedNavigation = navigation.current,
      startedHash = window.location.hash;
    try {
      if (
        !title.trim() ||
        Array.from(title).length > 2000 ||
        Array.from(locator).length > 2000 ||
        !validUnicode(title) ||
        !validUnicode(locator)
      )
        throw new ApiError(t("intakeMetadataInvalid"), "invalid_source", 400);
      const encoded = mode === "paste" ? encodePaste(text) : file;
      if (!encoded)
        throw new ApiError(t("intakeFileRequired"), "invalid_source", 400);
      const payload: IntakePayload = {
        title,
        locator,
        reading_scope: scope,
        input_kind: mode,
        format: encoded.format,
        content_base64: encoded.content_base64,
      };
      const result = await recovery.submit(payload);
      if (!alive.current) return;
      setRequestKey(result.key);
      if (result.saved) {
        setFinished(true);
        if (
          navigation.current === startedNavigation &&
          window.location.hash === startedHash
        )
          onOpen(result.saved);
      }
    } catch (error) {
      if (alive.current) setError(error);
    } finally {
      locked.current = false;
      if (alive.current) setSaving(false);
    }
  }
  return (
    <section className="panel" aria-label={t("intakeAdd")}>
      <h2>{t("intakeAdd")}</h2>
      <p>{t("intakeScopeNote")}</p>
      <div className="field">
        <label htmlFor={id + "-mode"}>{t("intakeInput")}</label>
        <select
          id={id + "-mode"}
          value={mode}
          disabled={disabled}
          onChange={(e) => changeMode(e.target.value as "paste" | "file")}
        >
          <option value="paste">{t("intakePasteMode")}</option>
          <option value="file">{t("intakeFileMode")}</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor={id + "-title"}>{t("intakeTitle")}</label>
        <input
          id={id + "-title"}
          value={title}
          disabled={disabled}
          onChange={(e) => setTitle(e.target.value)}
          required
        />
      </div>
      <div className="field">
        <label htmlFor={id + "-locator"}>{t("intakeLocator")}</label>
        <input
          id={id + "-locator"}
          value={locator}
          disabled={disabled}
          onChange={(e) => setLocator(e.target.value)}
        />
        <p>{t("intakeLocatorNote")}</p>
      </div>
      <div className="field">
        <label htmlFor={id + "-scope"}>{t("intakeDeclaredScope")}</label>
        <select
          id={id + "-scope"}
          value={scope}
          disabled={disabled}
          onChange={(e) => setScope(e.target.value as "unknown" | "abstract")}
        >
          <option value="unknown">{t("intakeScopeUnknown")}</option>
          <option value="abstract">{t("intakeScopeAbstract")}</option>
        </select>
      </div>
      {mode === "paste" ? (
        <div className="field field-wide">
          <label htmlFor={id + "-text"}>{t("intakePaste")}</label>
          <textarea
            id={id + "-text"}
            rows={10}
            value={text}
            disabled={disabled}
            onChange={(e) => setText(e.target.value)}
          />
          <p>{t("intakePasteNote")}</p>
        </div>
      ) : (
        <div className="field field-wide">
          <label htmlFor={id + "-file"}>{t("intakeFile")}</label>
          <input
            id={id + "-file"}
            type="file"
            accept=".txt,.md"
            disabled={disabled}
            onChange={(e) => void chooseFile(e.target.files?.[0])}
          />
          <p>{t("intakeFileNote")}</p>
          {reading && <p role="status">{t("loading")}</p>}
          {file && (
            <>
              <p>
                {filename} · {file.bytes} {t("intakeBytes")}
              </p>
              <h3>{t("intakeLocalPreview")}</h3>
              <ReadText value={file.text} />
            </>
          )}
        </div>
      )}
      {error !== undefined && <ErrorMessage error={error} t={t} />}
      {saving && <p role="status">{t("intakeSavingLeave")}</p>}
      {recovery.blocked && <p>{t("intakeResolveFirst")}</p>}
      {finished && <p>{t("intakeFound")}</p>}
      <button
        className="button primary"
        disabled={
          disabled ||
          reading ||
          !title.trim() ||
          (mode === "file" ? !file : !text.trim())
        }
        onClick={() => void save()}
      >
        {t("intakeSave")}
      </button>
      <button className="button secondary" onClick={onClose}>
        {t("cancel")}
      </button>
    </section>
  );
}
