import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { Translate } from "./i18n";
import type { Workspace } from "./types";

/** Guidance only: never reads credentials, starts setup, or probes a provider. */
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
            <ul>
              {services.map(([key, label, href, guidance]) => {
                const status =
                  snapshot?.schema_version === 1 &&
                  snapshot.source === "saved_local_setup_snapshot" &&
                  snapshot.freshness === "saved"
                    ? snapshot.components?.[key]
                    : "unknown";
                return (
                  <li key={key}>
                    <strong>{label}</strong>:{" "}
                    {t(
                      typeof status === "string" &&
                        Object.hasOwn(statuses, status)
                        ? statuses[status as keyof typeof statuses]
                        : "snapshotUnknown",
                    )}
                    <p>
                      {t(guidance)}{" "}
                      <a href={href} target="_blank" rel="noopener noreferrer">
                        {t("integrationOfficial")} — {label}
                      </a>
                    </p>
                  </li>
                );
              })}
            </ul>
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
            <p>
              {t("integrationNlmReconnect")}{" "}
              <code>python -m research_hub notebooklm login --auto-detect</code>
            </p>
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
