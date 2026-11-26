import { useEffect, useId, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { createPortal } from "react-dom";
import { obsidianStatusLabel, type Translate } from "./i18n";
import type { IntegrationLiveState, Workspace } from "./types";
import { NotebookLmAuthControls } from "./NotebookLmAuthControls";
import { ObsidianValidationForm } from "./ObsidianValidationForm";
import { ZoteroLibraryForm } from "./ZoteroLibraryForm";

function observationTime(value: unknown): string | null {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(value)) return null;
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return null;
  const normalized = date.toISOString();
  return normalized.slice(0, 19) === value.slice(0, 19) ? value : null;
}

/** Local connections setup, encrypted credentials, NLM login, and scoped Obsidian validation. */
export function IntegrationsSetup({
  workspace,
  t,
  projectId = "",
  liveState,
  onLiveStateChange,
}: {
  workspace: Workspace | null;
  t: Translate;
  projectId?: string;
  liveState?: IntegrationLiveState;
  onLiveStateChange?: Dispatch<SetStateAction<IntegrationLiveState>>;
}) {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const panelId = useId();
  const previousProject = useRef(projectId);
  const close = () => {
    setOpen(false);
    trigger.current?.focus();
  };
  useEffect(() => {
    if (open) heading.current?.focus();
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (
        target instanceof Node &&
        !panel.current?.contains(target) &&
        !trigger.current?.contains(target)
      ) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        close();
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);
  useEffect(() => {
    const navigate = () => setOpen(false); // Never steal focus from newer navigation.
    window.addEventListener("hashchange", navigate);
    window.addEventListener("popstate", navigate);
    return () => {
      window.removeEventListener("hashchange", navigate);
      window.removeEventListener("popstate", navigate);
    };
  }, []);
  useEffect(() => {
    if (previousProject.current !== projectId) setOpen(false);
    previousProject.current = projectId;
  }, [projectId]);
  const snapshot = workspace?.setup_snapshot;
  const knownSnapshot = snapshot?.schema_version === 1 && snapshot.source === "saved_local_setup_snapshot";
  const freshnessLabels = {
    saved: "integrationFreshSaved", stale: "integrationFreshStale", missing: "integrationFreshMissing",
    invalid: "integrationFreshInvalid", clock_skew: "integrationFreshClockSkew",
  } as const;
  const observedAt = knownSnapshot && (snapshot.freshness === "saved" || snapshot.freshness === "stale")
    ? observationTime(snapshot.observed_at) : null;
  const freshness = knownSnapshot && typeof snapshot.freshness === "string" && Object.hasOwn(freshnessLabels, snapshot.freshness)
    ? ((snapshot.freshness === "saved" || snapshot.freshness === "stale") && !observedAt ? "invalid" : snapshot.freshness)
    : "invalid";
  const vault = workspace?.capabilities?.obsidian_validation;
  const selectedVault = vault?.version === 1 && vault.status === "available" && vault.read_only === true &&
    vault.scope === "startup_selected_exact_vault" && typeof vault.authorized_vault === "string" && Boolean(vault.authorized_vault.trim());
  const localCap = liveState?.credentials ?? workspace?.capabilities?.local_integrations;
  const zoteroConnectionText = liveState?.zotero
    ? t(
        liveState.zotero.status === "connected_local_and_web"
          ? "integrationZoteroConnectedBoth"
          : liveState.zotero.status === "connected_web"
            ? "integrationZoteroConnectedWeb"
            : liveState.zotero.status === "connected_local"
              ? "integrationZoteroConnectedLocal"
              : liveState.zotero.status === "auth_failed"
                ? "integrationZoteroAuthFailed"
                : liveState.zotero.status === "missing_credentials"
                  ? "integrationZoteroMissingCreds"
                  : "integrationZoteroUnreachable",
      )
    : t("integrationNotChecked");
  const nlmConnectionText = liveState?.notebooklm
    ? t(
        liveState.notebooklm.status === "authenticated"
          ? "integrationNlmAuthenticated"
          : liveState.notebooklm.status === "expired"
            ? "integrationNlmExpired"
            : "integrationNlmMissing",
      )
    : t("integrationNotChecked");
  const obsidianConnectionText = liveState?.obsidian
    ? obsidianStatusLabel(liveState.obsidian, t)
    : t("integrationNotChecked");
  const compactParts: string[] = [];
  if (liveState?.zotero) {
    const ok = ["connected_local_and_web", "connected_web", "connected_local"].includes(liveState.zotero.status);
    compactParts.push(t(ok ? "integrationSummaryZoteroOk" : "integrationSummaryZoteroIssue"));
  }
  if (liveState?.obsidian) {
    compactParts.push(
      t(liveState.obsidian.status === "valid" ? "integrationSummaryObsidianOk" : "integrationSummaryObsidianIssue"),
    );
  }
  if (liveState?.notebooklm) {
    compactParts.push(
      t(liveState.notebooklm.status === "authenticated" ? "integrationSummaryNlmOk" : "integrationSummaryNlmIssue"),
    );
  }
  const compactSummaryText = compactParts.length ? compactParts.join(" · ") : t("integrationCompact");

  const hasLiveProbe = Boolean(liveState?.zotero || liveState?.obsidian || liveState?.notebooklm);
  const hasLiveIssue = Boolean(
    (liveState?.zotero && !["connected_local_and_web", "connected_web", "connected_local"].includes(liveState.zotero.status)) ||
    (liveState?.obsidian && liveState.obsidian.status !== "valid") ||
    (liveState?.notebooklm && liveState.notebooklm.status !== "authenticated"),
  );
  const statuses = {
    passed: "snapshotPassed",
    failed: "snapshotFailed",
    cancelled: "snapshotCancelled",
    skipped: "snapshotSkipped",
    unknown: "snapshotUnknown",
  } as const;
  const services = [
    [
      "vault",
      "Obsidian",
      "https://help.obsidian.md/manage-vaults",
      "integrationVault",
    ],
    [
      "zotero",
      "Zotero",
      "https://www.zotero.org/settings/keys",
      "integrationZotero",
    ],
    [
      "notebooklm_auth",
      "NotebookLM",
      "https://notebook.google.com/",
      "integrationNlm",
    ],
  ] as const;
  return (
    <>
      <div className="integration-entry">
        <button
          ref={trigger}
          type="button"
          className="button secondary icon-btn"
          title={compactSummaryText}
          aria-label={t("integrationsSetup")}
          data-tooltip={t("integrationsSetup")}
          data-tooltip-pos="top-start"
          aria-expanded={open}
          aria-controls={open ? panelId : undefined}
          onClick={() => (open ? close() : setOpen(true))}
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
            focusable="false"
          >
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
          {hasLiveProbe && <span className={`setup-dot ${hasLiveIssue ? "warn" : "ok"}`} aria-hidden="true" />}
        </button>
      </div>
      {open &&
        createPortal(
          <section
            ref={panel}
            id={panelId}
            role="dialog"
            aria-modal="false"
            aria-labelledby={panelId + "-title"}
            className="integrations-panel"
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.stopPropagation();
                close();
              }
            }}
          >
            <header className="integrations-panel-header">
              <h2 ref={heading} id={panelId + "-title"} tabIndex={-1}>
                {t("integrationsSetup")}
              </h2>
              <button
                type="button"
                className="button secondary small icon-btn"
                onClick={close}
                aria-label={t("integrationClose")}
                data-tooltip={t("integrationClose")}
                data-tooltip-pos="bottom-end"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true" focusable="false">
                  <path d="M18 6 6 18" />
                  <path d="m6 6 12 12" />
                </svg>
              </button>
            </header>
            <p className="small muted">{t("integrationsOptional")}</p>
            {compactParts.length > 0 && (
              <p className="small" role="status">{compactSummaryText}</p>
            )}
            <ul className="integration-tools">
              {services.map(([key, label, href, guidance]) => {
                const status =
                  knownSnapshot && freshness === "saved"
                    ? snapshot.components?.[key]
                    : "unknown";
                const connText =
                  key === "zotero"
                    ? zoteroConnectionText
                    : key === "notebooklm_auth"
                      ? nlmConnectionText
                      : obsidianConnectionText;
                const connTone =
                  key === "zotero" && liveState?.zotero
                    ? ["connected_local_and_web", "connected_web", "connected_local"].includes(liveState.zotero.status) ? "good" : "warn"
                    : key === "notebooklm_auth" && liveState?.notebooklm
                      ? liveState.notebooklm.status === "authenticated" ? "good" : "warn"
                      : key === "vault" && liveState?.obsidian
                        ? liveState.obsidian.status === "valid" ? "good" : "warn"
                        : "neutral";
                return (
                  <li key={key} className="integration-tool">
                    <div className="setup-tool-header">
                      <h3>{label}</h3>
                      <span className={`badge ${connTone}`}>{connText}</span>
                    </div>
                    <p className="small muted">
                      {t(guidance)}{" "}
                      <a href={href} target="_blank" rel="noopener noreferrer">
                        {t("integrationOfficial")}
                      </a>
                    </p>
                    {key === "vault" && (
                      <ObsidianValidationForm
                        capability={
                          workspace?.capabilities?.obsidian_validation
                        }
                        onValidated={(obsidian) =>
                          onLiveStateChange?.((prev) => ({
                            ...prev,
                            obsidian,
                          }))
                        }
                        t={t}
                      />
                    )}
                    {key === "zotero" && (
                      <ZoteroLibraryForm
                        t={t}
                        capability={localCap}
                        probe={liveState?.zotero}
                        onCredentialsSaved={(creds, zoteroTouched) =>
                          onLiveStateChange?.((prev) => ({
                            ...prev,
                            credentials: creds,
                            ...(zoteroTouched ? { zotero: null } : {}),
                          }))
                        }
                        onProbeUpdated={(probe) =>
                          onLiveStateChange?.((prev) => ({
                            ...prev,
                            zotero: probe,
                          }))
                        }
                      />
                    )}
                    {key === "notebooklm_auth" && (
                      <NotebookLmAuthControls
                        capability={localCap}
                        probe={liveState?.notebooklm}
                        loginJob={liveState?.loginJob}
                        onLoginJobChange={(job) =>
                          onLiveStateChange?.((prev) => ({
                            ...prev,
                            loginJob: job,
                          }))
                        }
                        onProbeUpdated={(probe) =>
                          onLiveStateChange?.((prev) => ({
                            ...prev,
                            notebooklm: probe,
                          }))
                        }
                        t={t}
                      />
                    )}
                    <dl className="integration-status">
                      <div><dt>{t("integrationSelectedDestination")}</dt><dd>{t(key === "vault" ? selectedVault ? "integrationSelectedVault" : "integrationNoStartupVault" : "integrationDestinationUnknown")}</dd></div>
                      <div><dt>{t("integrationCurrentConnection")}</dt><dd>{connText}</dd></div>
                      <div>
                        <dt>{t("integrationSavedObservation")}</dt>
                        <dd>
                          {t(
                            typeof status === "string" &&
                              Object.hasOwn(statuses, status)
                              ? statuses[status as keyof typeof statuses]
                              : "snapshotUnknown",
                          )}
                        </dd>
                      </div>
                    </dl>
                  </li>
                );
              })}
            </ul>
            <details className="setup-diagnostics">
              <summary>{t("integrationAdvancedSetup")}</summary>
              <p>{t("integrationsHistorical")}</p>
              <dl className="integration-status" aria-label={t("integrationObservationDetails")}>
                <div><dt>{t("integrationObservationSource")}</dt><dd>{t(knownSnapshot ? "integrationSavedSetupSource" : "integrationObservationUnavailable")}</dd></div>
                <div><dt>{t("integrationObservedAt")}</dt><dd>{observedAt ? <time dateTime={observedAt}>{observedAt}</time> : t("integrationObservationUnavailable")}</dd></div>
                <div><dt>{t("integrationObservationFreshness")}</dt><dd>{t(snapshot ? freshnessLabels[freshness] : "integrationFreshMissing")}</dd></div>
              </dl>
              <ol>
                <li>
                  {t("integrationSetupStep")}{" "}
                  <code>python -m research_hub setup</code>
                </li>
                <li>{t("integrationReuse")}</li>
                <li>
                  {t("integrationCheck")}{" "}
                  <code>python -m research_hub doctor</code>
                </li>
              </ol>
              <p>{t(localCap?.status === "available" ? "integrationLocalPrivacy" : "integrationPrivacy")}</p>
            </details>
            <a
              className="setup-guide-link"
              href="https://github.com/WenyuChiou/research-hub/blob/master/docs/setup.md"
              target="_blank"
              rel="noopener noreferrer"
            >
              {t("integrationGuide")}
            </a>
          </section>,
          document.body,
        )}
    </>
  );
}
