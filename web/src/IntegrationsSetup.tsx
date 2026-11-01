import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { Translate } from "./i18n";
import type { Workspace } from "./types";
import { ObsidianValidationForm } from "./ObsidianValidationForm";
import { ZoteroLibraryForm } from "./ZoteroLibraryForm";

function observationTime(value: unknown): string | null {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(value)) return null;
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return null;
  const normalized = date.toISOString();
  return normalized.slice(0, 19) === value.slice(0, 19) ? value : null;
}

/** Local drafts and scoped Obsidian validation; no credentials or provider probes. */
export function IntegrationsSetup({
  workspace,
  t,
  projectId = "",
}: {
  workspace: Workspace | null;
  t: Translate;
  projectId?: string;
}) {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
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
          className="button secondary"
          aria-expanded={open}
          aria-controls={open ? panelId : undefined}
          onClick={() => (open ? close() : setOpen(true))}
        >
          {t("integrationsSetup")}
        </button>
        <small>{t("integrationCompact")}</small>
      </div>
      {open &&
        createPortal(
          <section
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
              <button className="button" onClick={close}>
                {t("integrationClose")}
              </button>
            </header>
            <p>{t("integrationsOptional")}</p>
            <p>{t("integrationsHistorical")}</p>
            <dl className="integration-status" aria-label={t("integrationObservationDetails")}>
              <div><dt>{t("integrationObservationSource")}</dt><dd>{t(knownSnapshot ? "integrationSavedSetupSource" : "integrationObservationUnavailable")}</dd></div>
              <div><dt>{t("integrationObservedAt")}</dt><dd>{observedAt ? <time dateTime={observedAt}>{observedAt}</time> : t("integrationObservationUnavailable")}</dd></div>
              <div><dt>{t("integrationObservationFreshness")}</dt><dd>{t(snapshot ? freshnessLabels[freshness] : "integrationFreshMissing")}</dd></div>
            </dl>
            <ul className="integration-tools">
              {services.map(([key, label, href, guidance]) => {
                const status =
                  knownSnapshot && freshness === "saved"
                    ? snapshot.components?.[key]
                    : "unknown";
                return (
                  <li key={key} className="integration-tool">
                    <h3>{label}</h3>
                    <dl className="integration-status">
                      <div><dt>{t("integrationSelectedDestination")}</dt><dd>{t(key === "vault" ? selectedVault ? "integrationSelectedVault" : "integrationNoStartupVault" : "integrationDestinationUnknown")}</dd></div>
                      <div>
                        <dt>{t("integrationCurrentConnection")}</dt>
                        <dd>{t("integrationNotChecked")}</dd>
                      </div>
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
                    <p>
                      {t(guidance)}{" "}
                      <a href={href} target="_blank" rel="noopener noreferrer">
                        {t("integrationOfficial")} — {label}
                      </a>
                    </p>
                    {key === "vault" && (
                      <ObsidianValidationForm
                        capability={
                          workspace?.capabilities?.obsidian_validation
                        }
                        t={t}
                      />
                    )}
                    {key === "zotero" && <ZoteroLibraryForm t={t} />}
                    {key === "notebooklm_auth" && (
                      <>
                        <p>{t("integrationNlmPrerequisites")}</p>
                        <p>
                          {t("integrationNlmReconnect")}{" "}
                          <code>
                            {"python -m research_hub notebooklm login --auto-detect"}
                          </code>
                        </p>
                      </>
                    )}
                  </li>
                );
              })}
            </ul>
            <h3>{t("integrationAdvancedSetup")}</h3>
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
            <p>{t("integrationPrivacy")}</p>
            <a
              href="https://github.com/WenyuChiou/research-hub/blob/fix/nlm-085-integrations-guidance/docs/setup.md"
              target="_blank"
              rel="noopener noreferrer"
            >
              {t("integrationGuide")} (SDK 0.8.5)
            </a>
          </section>,
          document.body,
        )}
    </>
  );
}
