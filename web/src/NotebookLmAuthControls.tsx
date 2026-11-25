import { useEffect, useId, useState } from "react";
import { ApiError, api } from "./api";
import type { Translate } from "./i18n";
import type { LocalIntegrationsCapability, NlmLoginJobState, NlmProbeResult } from "./types";

export function NotebookLmAuthControls({
  capability,
  probe,
  loginJob: controlledLoginJob,
  onLoginJobChange,
  onProbeUpdated,
  t,
}: {
  capability?: LocalIntegrationsCapability;
  probe?: NlmProbeResult | null;
  loginJob?: NlmLoginJobState | null;
  onLoginJobChange?: (job: NlmLoginJobState) => void;
  onProbeUpdated?: (probe: NlmProbeResult) => void;
  t: Translate;
}) {
  const id = useId();
  const enabled = capability?.status === "available";
  const [busy, setBusy] = useState(false);
  const [browser, setBrowser] = useState("");
  const [statePath, setStatePath] = useState("");
  const [showImport, setShowImport] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [localLoginJob, setLocalLoginJob] = useState<NlmLoginJobState | null>(null);
  const loginJob = controlledLoginJob ?? localLoginJob;

  function updateLoginJob(job: NlmLoginJobState) {
    setLocalLoginJob(job);
    onLoginJobChange?.(job);
  }

  useEffect(() => {
    if (!enabled || loginJob?.status !== "running") return;
    const timer = window.setInterval(() => {
      void (async () => {
        try {
          const st = await api<{
            ok: boolean;
            login_job?: NlmLoginJobState;
            probes?: { notebooklm_auth?: NlmProbeResult | null };
          }>("/integrations/status");
          if (st.login_job) {
            updateLoginJob(st.login_job);
            if (st.login_job.status === "succeeded") {
              setStatusMessage(t("integrationNlmAuthenticated"));
              setErrorMessage(null);
            } else if (st.login_job.status === "failed") {
              setErrorMessage(t("integrationNlmLoginFailed"));
              setStatusMessage(null);
            }
          }
          if (st.probes?.notebooklm_auth) {
            onProbeUpdated?.(st.probes.notebooklm_auth);
          }
        } catch {
          // Ignore transient status poll error while waiting for login window.
        }
      })();
    }, 2500);
    return () => window.clearInterval(timer);
  }, [enabled, loginJob?.status, onProbeUpdated, t]);

  function applyProbe(next: NlmProbeResult) {
    onProbeUpdated?.(next);
    if (next.status === "authenticated") {
      setStatusMessage(t("integrationNlmAuthenticated"));
      setErrorMessage(null);
    } else if (next.status === "expired") {
      setErrorMessage(t("integrationNlmExpired"));
      setStatusMessage(null);
    } else {
      setStatusMessage(t("integrationNlmMissing"));
      setErrorMessage(null);
    }
  }

  async function checkSession() {
    setBusy(true);
    setErrorMessage(null);
    setStatusMessage(null);
    try {
      const res = await api<{ ok: boolean; probe: NlmProbeResult }>("/integrations/notebooklm/check", {});
      if (res.probe) applyProbe(res.probe);
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : t("integrationNlmLoginFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function startBrowserLogin() {
    setBusy(true);
    setErrorMessage(null);
    setStatusMessage(null);
    try {
      const res = await api<{ ok: boolean; login: NlmLoginJobState }>("/integrations/notebooklm/login", {
        mode: "browser_window",
      });
      if (res.login) updateLoginJob(res.login);
      setStatusMessage(t("integrationNlmRunning"));
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : t("integrationNlmLoginFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function importCookies() {
    setBusy(true);
    setErrorMessage(null);
    setStatusMessage(null);
    try {
      const res = await api<{ ok: boolean; probe?: NlmProbeResult; error?: string }>(
        "/integrations/notebooklm/login",
        { mode: "browser_cookies", browser },
      );
      if (res.probe) applyProbe(res.probe);
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : t("integrationNlmLoginFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function importStateFile() {
    if (!statePath.trim()) {
      setErrorMessage(t("integrationNlmStatePathLabel"));
      return;
    }
    setBusy(true);
    setErrorMessage(null);
    setStatusMessage(null);
    try {
      const res = await api<{ ok: boolean; probe?: NlmProbeResult; error?: string }>(
        "/integrations/notebooklm/login",
        { mode: "import_state", state_path: statePath.trim() },
      );
      if (res.probe) applyProbe(res.probe);
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : t("integrationNlmLoginFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="notebooklm-auth-controls">
      <p>{t("integrationNlmPrerequisites")}</p>
      {enabled ? (
        <>
          <div className="integration-form-actions">
            <button type="button" className="button secondary" disabled={busy} onClick={() => void checkSession()}>
              {busy ? t("integrationChecking") : t("integrationNlmCheck")}
            </button>
            <button type="button" className="button primary" disabled={busy || loginJob?.status === "running"} onClick={() => void startBrowserLogin()}>
              {t("integrationNlmOpenBrowser")}
            </button>
            <button type="button" className="button secondary" disabled={busy} onClick={() => void importCookies()}>
              {t("integrationNlmImportCookies")}
            </button>
            <button type="button" className="button text-button" disabled={busy} onClick={() => setShowImport((v) => !v)}>
              {t("integrationNlmImportFile")}
            </button>
          </div>
          <div className="integration-form-fields">
            <label htmlFor={id + "-browser"}>
              {t("integrationNlmBrowserSelect")}
              <select
                id={id + "-browser"}
                value={browser}
                onChange={(e) => setBrowser(e.target.value)}
              >
                <option value="">{t("integrationNlmBrowserAuto")}</option>
                <option value="chrome">Chrome</option>
                <option value="edge">Edge</option>
                <option value="firefox">Firefox</option>
                <option value="chromium">Chromium</option>
              </select>
            </label>
            {showImport && (
              <label htmlFor={id + "-state-path"}>
                {t("integrationNlmStatePathLabel")}
                <div className="integration-inline-row">
                  <input
                    id={id + "-state-path"}
                    type="text"
                    value={statePath}
                    autoComplete="off"
                    spellCheck={false}
                    onChange={(e) => setStatePath(e.target.value)}
                  />
                  <button type="button" className="button secondary" disabled={busy} onClick={() => void importStateFile()}>
                    {t("integrationNlmImportFile")}
                  </button>
                </div>
              </label>
            )}
          </div>
          {statusMessage && <p role="status" className="small">{statusMessage}</p>}
          {errorMessage && <p role="alert" className="small bad-text">{errorMessage}</p>}
          {!statusMessage && !errorMessage && probe && (
            <p role="status" className="small">
              {t(
                probe.status === "authenticated"
                  ? "integrationNlmAuthenticated"
                  : probe.status === "expired"
                    ? "integrationNlmExpired"
                    : "integrationNlmMissing",
              )}
            </p>
          )}
        </>
      ) : (
        <p>
          {t("integrationNlmReconnect")}{" "}
          <code>{"python -m research_hub notebooklm login --auto-detect"}</code>
        </p>
      )}
    </div>
  );
}
