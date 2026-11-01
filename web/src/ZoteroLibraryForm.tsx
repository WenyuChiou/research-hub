import { useId, useRef, useState, type FormEvent } from "react";
import type { Translate } from "./i18n";

type LibraryType = "" | "user" | "group";
type Preview = { libraryId: string; libraryType: Exclude<LibraryType, ""> };

/** A numeric draft check only; does not read config, save, or contact Zotero. */
export function ZoteroLibraryForm({ t }: { t: Translate }) {
  const id = useId();
  const libraryInput = useRef<HTMLInputElement>(null);
  const typeInput = useRef<HTMLSelectElement>(null);
  const [libraryId, setLibraryId] = useState("");
  const [libraryType, setLibraryType] = useState<LibraryType>("");
  const [checked, setChecked] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const trimmed = libraryId.trim();
  // Keep IDs as strings: a library ID can exceed JavaScript's safe integer range.
  const idValid = /^[0-9]+$/.test(trimmed) && /[1-9]/.test(trimmed);
  const typeValid = libraryType === "user" || libraryType === "group";

  function check(event: FormEvent) {
    event.preventDefault();
    setChecked(true);
    if (!idValid || !typeValid) {
      setPreview(null);
      if (!idValid) libraryInput.current?.focus();
      else typeInput.current?.focus();
      return;
    }
    setPreview({ libraryId: trimmed.replace(/^0+/, ""), libraryType });
  }
  function reset() {
    setLibraryId("");
    setLibraryType("");
    setChecked(false);
    setPreview(null);
    libraryInput.current?.focus();
  }
  function changed() {
    setChecked(false);
    setPreview(null);
  }

  return (
    <form
      className="zotero-library-form"
      aria-label={t("zoteroDraft")}
      onSubmit={check}
      noValidate
    >
      <p id={id + "-help"} className="small">
        {t("zoteroDraftHelp")}
      </p>
      <div className="integration-form-fields">
        <label htmlFor={id + "-library"}>
          {t("zoteroLibraryId")}
          <input
            ref={libraryInput}
            id={id + "-library"}
            name="zotero_library_id"
            type="text"
            inputMode="numeric"
            autoComplete="off"
            spellCheck={false}
            value={libraryId}
            aria-required="true"
            aria-invalid={checked && !idValid}
            aria-describedby={
              id + "-help" + (checked && !idValid ? " " + id + "-id-error" : "")
            }
            onChange={(event) => {
              setLibraryId(event.target.value);
              changed();
            }}
          />
        </label>
        <label htmlFor={id + "-type"}>
          {t("zoteroLibraryType")}
          <select
            ref={typeInput}
            id={id + "-type"}
            name="zotero_library_type"
            value={libraryType}
            aria-required="true"
            aria-invalid={checked && !typeValid}
            aria-describedby={
              checked && !typeValid ? id + "-type-error" : undefined
            }
            onChange={(event) => {
              setLibraryType(event.target.value as LibraryType);
              changed();
            }}
          >
            <option value="">{t("zoteroChooseType")}</option>
            <option value="user">{t("zoteroUserLibrary")}</option>
            <option value="group">{t("zoteroGroupLibrary")}</option>
          </select>
        </label>
      </div>
      {checked && !idValid && (
        <p id={id + "-id-error"} role="alert">
          {t("zoteroInvalidId")}
        </p>
      )}
      {checked && !typeValid && (
        <p id={id + "-type-error"} role="alert">
          {t("zoteroMissingType")}
        </p>
      )}
      <div className="integration-form-actions">
        <button className="button secondary" type="submit">
          {t("zoteroCheckFormat")}
        </button>
        <button className="button text-button" type="button" onClick={reset}>
          {t("cancel")}
        </button>
      </div>
      <p role="status">
        {preview ? t("zoteroFormatValid") : t("zoteroNotChecked")}
      </p>
      {preview && (
        <dl
          className="integration-draft-preview"
          aria-label={t("zoteroDraftPreview")}
        >
          <div>
            <dt>{t("zoteroLibraryId")}</dt>
            <dd>{preview.libraryId}</dd>
          </div>
          <div>
            <dt>{t("zoteroLibraryType")}</dt>
            <dd>
              {t(
                preview.libraryType === "user"
                  ? "zoteroUserLibrary"
                  : "zoteroGroupLibrary",
              )}
            </dd>
          </div>
        </dl>
      )}
    </form>
  );
}
