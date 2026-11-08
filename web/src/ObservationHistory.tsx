import { ReadText, SourceLink } from "./components";
import type { Translate } from "./i18n";
import type { ResearchRecord } from "./types";
import { sourceObservations, type ObservationTextContext } from "./sourceObservations";

export function SourceObservations({ record, context, t }: { record: ResearchRecord; context?: ObservationTextContext; t: Translate }) {
  const view = sourceObservations(record, context);
  if (!view.observations.length) return null;
  const unknown = t("observationUnknown");
  return <section className="source-observations" aria-label={t("observationHistory")}>
    <h4>{t("observationHistory")}</h4>
    <p className="small muted">{t("observationHelp")}</p>
    {view.versionPending && <p className="catalog-missing">{t("observationVersionPending")}</p>}
    {view.hasSavedProvenance && <p className="small">{t("observationProvenance")}</p>}
    {view.observations.map((obs, index) => <details className="source-observation" data-generated={obs.generated ? "true" : undefined} key={index}>
      <summary>{obs.generated ? t("observationGenerated") : t("observationOther")} · {obs.id ?? unknown}</summary>
      {obs.generated && <div className="observation-reading">
        <p className="small muted">{t(obs.binding === "bound-report" ? "observationBound" : "observationUnbound")}</p>
        {obs.body ? <ReadText value={obs.body} /> : <p className="catalog-missing">{t("observationBodyUnknown")}</p>}
        <p className="small">{t("observationSources")}</p>
        {obs.reportedSources.length > 0 ? <ul>{obs.reportedSources.map((url, i) => <li key={i}><SourceLink locator={url} /></li>)}</ul> : <p>{unknown}</p>}
      </div>}
      <details className="observation-provenance">
      <summary>{t("observationDetails")}</summary>
      <dl>
        <dt>{t("observationLevel")}</dt><dd>{obs.evidenceLevel ?? unknown}</dd>
        <dt>{t("observationOriginalReading")}</dt><dd>{view.originalReading ?? unknown}</dd>
        <dt>{t("observationVersion")}</dt><dd>{obs.version ?? unknown} · {obs.versionReviewed ? t("observationReviewRef") : t("observationVersionPending")}</dd>
        <dt>{t("observationReference")}</dt><dd>{obs.referencePresent ? t("observationReferencePresent") : unknown}</dd>
        <dt>{t("observationTextHash")}</dt><dd>{obs.textHash ? <code>{obs.textHash}</code> : unknown}</dd>
      </dl>
      {obs.generated && <>
        <dl>
          <dt>{t("observationReportedTime")}</dt><dd>{obs.reportedAt ?? unknown}</dd>
          <dt>{t("observationReportedReading")}</dt><dd>{obs.reportedReading ?? unknown}</dd>
          <dt>{t("observationRole")}</dt><dd>{obs.roleSuggestion ?? unknown}</dd>
        </dl>
      </>}
      </details>
    </details>)}
  </section>;
}
