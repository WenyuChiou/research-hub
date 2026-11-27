import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { ApiError, api, recoverCsrfIfForbidden } from "./api";
import type { Translate } from "./i18n";
import type { LocalIntegrationsCapability, ZoteroProbeResult } from "./types";

type LibraryType = "" | "user" | "group";
type Preview = { libraryId: string; libraryType: Exclude<LibraryType, ""> };

function zoteroProbeLabel(status: ZoteroProbeResult["status"], t: Translate): string {
  switch (status) {
    case "connected_local_and_web":
      return t("integrationZoteroConnectedBoth");
    case "connected_web":
      return t("integrationZoteroConnectedWeb");
    case "connected_local":
      return t("integrationZoteroConnectedLocal");
    case "auth_failed":
      return t("integrationZoteroAuthFailed");
    case "missing_credentials":
      return t("integrationZoteroMissingCreds");
    default:
      return t("integrationZoteroUnreachable");
  }
}

/** Zotero library format check plus optional encrypted local credentials & probe. */
export function ZoteroLibraryForm({
  t,
  capability,
  probe,
  onCredentialsSaved,
  onProbeUpdated,
}: {
  t: Translate;
  capability?: LocalIntegrationsCapability;
  probe?: ZoteroProbeResult | null;
  onCredentialsSaved?: (creds: LocalIntegrationsCapability, zoteroTouched: boolean) => void;
  onProbeUpdated?: (probe: ZoteroProbeResult) => void;
}) {
  const id = useId();
  const enabled = capability?.status === "available";
  const libraryInput = useRef<HTMLInputElement>(null);
  const typeInput = useRef<HTMLSelectElement>(null);
  const [libraryId, setLibraryId] = useState(capability?.zotero_library_id ?? "");
  const [libraryType, setLibraryType] = useState<LibraryType>(
    capability?.zotero_library_type ?? "",
  );
  const [zoteroApiKey, setZoteroApiKey] = useState("");
  const [unpaywallEmail, setUnpaywallEmail] = useState("");
  const [s2ApiKey, setS2ApiKey] = useState("");
  const [checked, setChecked] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) return;
    if (capability?.zotero_library_id) setLibraryId(capability.zotero_library_id);
    if (capability?.zotero_library_type) setLibraryType(capability.zotero_library_type);
  }, [enabled, capability?.zotero_library_id, capability?.zotero_library_type]);

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
    setZoteroApiKey("");
    setUnpaywallEmail("");
    setS2ApiKey("");
    setChecked(false);
    setPreview(null);
    setSaveMessage(null);
    setSaveError(null);
    libraryInput.current?.focus();
  }
  function changed() {
    setChecked(false);
    setPreview(null);
  }

  async function saveCredentials() {
    if (!enabled) return;
    setSaveMessage(null);
    setSaveError(null);
    const payload: Record<string, unknown> = {};
    if (trimmed) {
      if (!idValid) {
        setChecked(true);
        libraryInput.current?.focus();
        return;
      }
      payload.zotero_library_id = trimmed.replace(/^0+/, "");
    }
    if (libraryType) {
      payload.zotero_library_type = libraryType;
    }
    if (zoteroApiKey.trim()) {
      payload.zotero_api_key = zoteroApiKey.trim();
    }
    if (unpaywallEmail.trim()) {
      payload.unpaywall_email = unpaywallEmail.trim();
    }
    if (s2ApiKey.trim()) {
      payload.s2_api_key = s2ApiKey.trim();
    }
    if (!Object.keys(payload).length) {
      setSaveError(t("integrationSaveFailed"));
      return;
    }
    setBusy(true);
    try {
      const res = await api<{ ok: boolean; zotero_touched?: boolean; credentials?: LocalIntegrationsCapability }>(
        "/integrations/credentials",
        payload,
      );
      const touched = typeof res.zotero_touched === "boolean" ? res.zotero_touched : Boolean(payload.zotero_api_key);
      if (res.credentials) onCredentialsSaved?.(res.credentials, touched);
      setZoteroApiKey("");
      setS2ApiKey("");
      setSaveMessage(t("integrationSaved"));
    } catch (err) {
      void recoverCsrfIfForbidden(err);
      setSaveError(err instanceof ApiError ? err.message : t("integrationSaveFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function clearSavedKey(which: "clear_zotero_api_key" | "clear_s2_api_key") {
    if (!enabled) return;
    setBusy(true);
    setSaveMessage(null);
    setSaveError(null);
    try {
      const res = await api<{ ok: boolean; zotero_touched?: boolean; credentials?: LocalIntegrationsCapability }>(
        "/integrations/credentials",
        { [which]: true },
      );
      const touched = typeof res.zotero_touched === "boolean" ? res.zotero_touched : which === "clear_zotero_api_key";
      if (res.credentials) onCredentialsSaved?.(res.credentials, touched);
      setSaveMessage(t("integrationSaved"));
    } catch (err) {
      void recoverCsrfIfForbidden(err);
      setSaveError(err instanceof ApiError ? err.message : t("integrationSaveFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function checkZotero() {
    if (!enabled) return;
    setBusy(true);
    setSaveError(null);
    try {
      const res = await api<{ ok: boolean; probe?: ZoteroProbeResult }>(
        "/integrations/zotero/check",
        {},
      );
      if (res.probe) onProbeUpdated?.(res.probe);
    } catch (err) {
      void recoverCsrfIfForbidden(err);
      setSaveError(err instanceof ApiError ? err.message : t("integrationZoteroUnreachable"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      className="zotero-library-form"
      aria-label={t("zoteroDraft")}
      onSubmit={check}
      noValidate
    >
      <p id={id + "-help"} className="small">
        {t(enabled ? "zoteroLocalCredentialsHelp" : "zoteroDraftHelp")}
      </p>
      {enabled && capability?.zotero_credential_source && capability.zotero_credential_source !== "none" && (
        <p className="small muted">
          <span className="badge neutral">
            {t(
              capability.zotero_credential_source === "config"
                ? "zoteroSourceConfig"
                : capability.zotero_credential_source === "env"
                  ? "zoteroSourceEnv"
                  : "zoteroSourceLegacy",
            )}
          </span>
          {capability.zotero_env_overridden ? ` · ${t("zoteroEnvOverriddenNote")}` : ""}
        </p>
      )}
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
        {enabled && (
          <>
            <label htmlFor={id + "-api-key"} className="field-wide">
              {t("integrationApiKeyLabel")}
              <span className="small muted">
                {" "}
                ({capability?.zotero_api_key_present ? t("integrationKeyPresent") : t("integrationKeyMissing")})
              </span>
              <input
                id={id + "-api-key"}
                name="zotero_api_key"
                type="password"
                autoComplete="off"
                spellCheck={false}
                placeholder={capability?.zotero_api_key_present ? t("integrationApiKeyHint") : ""}
                value={zoteroApiKey}
                onChange={(event) => setZoteroApiKey(event.target.value)}
              />
            </label>
          </>
        )}
      </div>
      {enabled && (
        <details className="integration-optional-keys">
          <summary>{t("integrationOptionalKeys")}</summary>
          <div className="integration-form-fields">
            <label htmlFor={id + "-unpaywall"}>
              {t("integrationUnpaywallLabel")}
              <span className="small muted">
                {" "}
                ({capability?.unpaywall_email_present ? t("integrationKeyPresent") : t("integrationKeyMissing")})
              </span>
              <input
                id={id + "-unpaywall"}
                name="unpaywall_email"
                type="email"
                autoComplete="off"
                spellCheck={false}
                placeholder={t("integrationUnpaywallPlaceholder")}
                value={unpaywallEmail}
                onChange={(event) => setUnpaywallEmail(event.target.value)}
              />
            </label>
            <label htmlFor={id + "-s2-key"}>
              {t("integrationS2KeyLabel")}
              <span className="small muted">
                {" "}
                ({capability?.s2_api_key_present ? t("integrationKeyPresent") : t("integrationKeyMissing")})
              </span>
              <input
                id={id + "-s2-key"}
                name="s2_api_key"
                type="password"
                autoComplete="off"
                spellCheck={false}
                placeholder={capability?.s2_api_key_present ? t("integrationApiKeyHint") : ""}
                value={s2ApiKey}
                onChange={(event) => setS2ApiKey(event.target.value)}
              />
            </label>
          </div>
          {(capability?.zotero_api_key_present || capability?.s2_api_key_present) && (
            <div className="integration-form-actions">
              {capability?.zotero_api_key_present && (
                <button
                  className="button text-button"
                  type="button"
                  disabled={busy}
                  onClick={() => void clearSavedKey("clear_zotero_api_key")}
                >
                  {t("integrationClearKey")} (Zotero)
                </button>
              )}
              {capability?.s2_api_key_present && (
                <button
                  className="button text-button"
                  type="button"
                  disabled={busy}
                  onClick={() => void clearSavedKey("clear_s2_api_key")}
                >
                  {t("integrationClearKey")} (Semantic Scholar)
                </button>
              )}
            </div>
          )}
        </details>
      )}
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
        {enabled && (
          <>
            <button
              className="button primary small"
              type="button"
              disabled={busy}
              onClick={() => void saveCredentials()}
            >
              {busy ? t("integrationSaving") : t("integrationSaveCredentials")}
            </button>
            <button
              className="button secondary small"
              type="button"
              disabled={busy}
              onClick={() => void checkZotero()}
            >
              {t("integrationCheckZotero")}
            </button>
          </>
        )}
        <button className="button secondary small" type="submit">
          {t("zoteroCheckFormat")}
        </button>
        <button className="button text-button small" type="button" onClick={reset}>
          {t("cancel")}
        </button>
      </div>
      {saveMessage && <p role="status" className="small good-text">{saveMessage}</p>}
      {saveError && <p role="alert" className="small bad-text">{saveError}</p>}
      {enabled && probe && (
        <p role="status" className="small">
          {zoteroProbeLabel(probe.status, t)}
        </p>
      )}
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
