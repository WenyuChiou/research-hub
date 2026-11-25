import { NativeSummaryReader } from "./NativeSummaryReader";
import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useCompactReadingLayout } from "./readingLayout";
import { MutationForm, ReadText, SourceLink } from "./components";
import { obsidianStatusLabel, statusLabel, type Translate } from "./i18n";
import type { IntegrationLiveState, ResearchRecord, Workspace } from "./types";
import { SourceObservations } from "./ObservationHistory";
import type { ObservationTextContext } from "./sourceObservations";
import { ObservationPreview, observationArtifacts, type ObservationReadScope } from "./ObservationPreview";
import { SavedWorkingSummary, WorkingSummaryEditor, workingSummary } from "./WorkingSummaryEditor";

const text = (value: unknown) => typeof value === "string" || typeof value === "number" ? String(value) : "";
const category = (record: ResearchRecord) => text(record.data.category).trim() || text(record.data.sub_category).trim();
const strings = (value: unknown) => Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
const savedSummary = (record: ResearchRecord) => [record.data.summary, record.data.abstract]
  .find((value): value is string => typeof value === "string" && Boolean(value.trim())) || "";
// Presence is intentionally separate from the guarded reader's current/stale/
// unavailable result and from human or scientific acceptance.
const registeredNativeSummary = (record: ResearchRecord) => record.kind === "source" &&
  "native_summary_available" in record && record.native_summary_available === true;
const missingSummary = (record: ResearchRecord) => !savedSummary(record) &&
  !workingSummary(record) && !registeredNativeSummary(record);
type Organization = "all" | "unclassified" | "missing-summary" | "unscreened";

function formatAuthors(value: unknown): string {
  if (typeof value === "string") return value.trim();
  if (!Array.isArray(value)) return "";
  const names = value.map((item) => {
    if (typeof item === "string") return item.trim();
    if (item && typeof item === "object") {
      const obj = item as Record<string, unknown>;
      const direct = text(obj.name).trim();
      if (direct) return direct;
      const family = text(obj.family).trim();
      const given = text(obj.given).trim();
      return [family, given].filter(Boolean).join(", ");
    }
    return "";
  }).filter(Boolean);
  if (!names.length) return "";
  return names.length > 2 ? `${names[0]} et al.` : names.join(", ");
}

function categoryName(value: string, t: Translate) {
  if (value === "human") return t("catalogHuman");
  if (value === "human-review") return t("catalogHumanReview");
  if (value === "llm") return t("catalogLlm");
  return value || t("catalogUnclassified");
}

function readingScope(record: ResearchRecord, t: Translate) {
  const scope = text(record.data.reading_level) || text(record.data.reading_scope);
  if (scope === "abstract-snippet") return t("catalogAbstractSnippet");
  if (scope === "abstract") return t("catalogAbstractOnly");
  if (scope === "metadata") return t("catalogMetadataOnly");
  if (scope === "note-metadata") return t("libraryMetadataOnly");
  if (scope === "full-text") return t("catalogFullTextDeclared");
  return t("catalogUnknownScope");
}

export function LiteratureLibrary({ sources, screenings, t, onScreen, onPrepare, matches, observationText, observationRead, pageSuspended, categoryHost, onWorkingSummarySaved, workspace, liveIntegrations }: {
  sources: ResearchRecord[];
  screenings: ResearchRecord[];
  t: Translate;
  onScreen: (sourceId: string, decision: string, rationale: string) => Promise<void>;
  onPrepare: (record: ResearchRecord) => void;
  matches?: Map<string, ResearchRecord[]>;
  observationText?: ObservationTextContext;
  observationRead?: ObservationReadScope;
  pageSuspended?: boolean;
  categoryHost?: HTMLElement | null;
  onWorkingSummarySaved?: () => Promise<void>;
  workspace?: Workspace | null;
  liveIntegrations?: IntegrationLiveState;
}) {
  const [query, setQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("");
  const [organization, setOrganization] = useState<Organization>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [readerOpen, setReaderOpen] = useState(false);
  const [selectionMissing, setSelectionMissing] = useState(false);
  const detailId = useId();
  const detailHeading = useRef<HTMLHeadingElement>(null);
  const selectedButton = useRef<HTMLButtonElement>(null);
  const observationReader = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const categorySelect = useRef<HTMLSelectElement>(null);
  const categoryControls = useRef<HTMLDivElement>(null);
  const reader = useRef<HTMLElement>(null);
  const lastReadingFocus = useRef<Element | null>(null);
  const moveFilterFocus = useRef<"select" | "buttons" | null>(null);
  const compact = useCompactReadingLayout(next => {
    if (!active) return;
    const focused = document.activeElement === document.body ? lastReadingFocus.current : document.activeElement;
    if (next && active) {
      if (reader.current?.contains(focused) && selected) {
        setSelectedId(selected.id); setReaderOpen(true);
      } else if (list.current?.contains(focused) ||
        searchInput.current === focused || categoryControls.current?.contains(focused)) {
        setReaderOpen(false);
      }
    }
    if (next && categoryControls.current?.contains(focused)) moveFilterFocus.current = "select";
    else if (!next && categorySelect.current === focused) moveFilterFocus.current = "buttons";
  });
  const returnRequested = useRef(false);
  const openDraftRequested = useRef(false);
  const returnPosition = useRef({page: 0, list: 0});
  const active = observationRead?.active !== false;
  const focusRequested = useRef(false);
  useEffect(() => {
    if (focusRequested.current) {
      focusRequested.current = false;
      detailHeading.current?.focus();
      if (openDraftRequested.current) { openDraftRequested.current = false; openDrafts(false); }
    }
  }, [selectedId, readerOpen]);
  const latestScreenings = new Map<string, ResearchRecord>();
  for (const screening of screenings) {
    if (screening.kind === "screening" && typeof screening.data.source_id === "string") {
      latestScreenings.set(screening.data.source_id, screening);
    }
  }
  const screenedDecision = (record: ResearchRecord): "include" | "exclude" | null => {
    const decision = latestScreenings.get(record.id)?.data;
    if (decision && (decision.decision === "include" || decision.decision === "exclude") && typeof decision.rationale === "string" && decision.rationale.trim()) {
      return decision.decision;
    }
    return null;
  };
  const screened = (record: ResearchRecord) => screenedDecision(record) !== null;
  const matchesOrganization = (record: ResearchRecord, value: Organization) =>
    value === "unclassified" ? !category(record)
      : value === "missing-summary" ? missingSummary(record)
        : value === "unscreened" ? record.kind === "source" && !screened(record) : true;
  const organizationViews = [
    ["all", "catalogAllMaterial"], ["unclassified", "catalogNeedsCategory"],
    ["missing-summary", "catalogNeedsSummary"], ["unscreened", "catalogNeedsScreening"],
  ] as const;
  const categories = [...new Set(sources.map(category).filter(Boolean))].sort();
  const search = query.trim().toLocaleLowerCase();
  const visible = sources.filter((record) =>
    matchesOrganization(record, organization) &&
    (!selectedCategory || category(record) === selectedCategory) &&
    (!search || [record.data.title, formatAuthors(record.data.authors), record.data.year, record.data.doi, record.data.venue, record.data.journal, record.data.relevance, category(record), ...strings(record.data.tags), ...strings(record.data.labels)]
      .map(text).join(" ").toLocaleLowerCase().includes(search)),
  );
  const exactSelected = visible.find((record) => record.id === selectedId);
  const selected = compact && readerOpen ? exactSelected : exactSelected ?? visible[0];
  useEffect(() => {
    if (compact && readerOpen && !exactSelected) {
      setSelectionMissing(true); returnRequested.current = true; setReaderOpen(false);
    }
  }, [compact, readerOpen, exactSelected]);
  useEffect(() => {
    if (!active) return;
    if (moveFilterFocus.current === "select" && compact) categorySelect.current?.focus();
    if (moveFilterFocus.current === "buttons" && !compact) categoryControls.current?.querySelector<HTMLButtonElement>('[aria-pressed="true"]')?.focus();
    moveFilterFocus.current = null;
    if (!readerOpen && returnRequested.current) {
      returnRequested.current = false;
      if (exactSelected) {
        selectedButton.current?.focus({preventScroll: true});
        if (list.current) list.current.scrollTop = returnPosition.current.list;
        window.scrollTo({top: returnPosition.current.page, behavior: "instant"});
      } else searchInput.current?.focus();
    }
  }, [readerOpen, compact, active, exactSelected]);
  const latest = selected ? latestScreenings.get(selected.id) : undefined;
  const selectedDecision = selected ? screenedDecision(selected) : null;
  const summary = selected && savedSummary(selected);
  const note = selected?.kind === "library-note";
  // Registered references are discoverable without fetching every row. They do
  // not assert that the report body is readable or that a summary was accepted.
  const draftScope = observationRead ?? (observationText ? {
    projectId: observationText.projectId, artifacts: observationText.artifacts, active: true,
  } : undefined);
  const registeredDrafts = new Set(sources.filter(record => observationArtifacts(record, draftScope).length > 0).map(record => record.id));
  function openDrafts(focus = true) {
    const entries = observationReader.current?.querySelectorAll<HTMLDetailsElement>('.source-observation[data-generated="true"]');
    entries?.forEach(entry => { entry.open = true; });
    if (focus) entries?.[0]?.querySelector<HTMLElement>(":scope > summary")?.focus();
  }
  const categoryFilters = <div ref={categoryControls} className="catalog-categories" role="group" aria-label={t("catalogCategories")} hidden={compact}>
    <h3>{t("catalogCategories")}</h3>
    <button type="button" aria-pressed={!selectedCategory} onClick={() => setSelectedCategory("")}>{t("catalogAllCategories")} <span>{sources.length}</span></button>
    {categories.map(value => <button type="button" key={value} aria-pressed={selectedCategory === value} onClick={() => setSelectedCategory(value)}>{categoryName(value,t)} <span>{sources.filter(record => category(record) === value).length}</span></button>)}
  </div>;

  const selectedAuthors = selected ? formatAuthors(selected.data.authors) : "";
  const selectedVenue = selected ? (text(selected.data.venue) || text(selected.data.journal)) : "";

  return (
    <section className={`literature-library${compact && readerOpen ? " is-reading" : ""}`} aria-label={t("catalogTitle")}
      onFocusCapture={event => { lastReadingFocus.current = event.target as Element; }}
      onBlurCapture={event => {
        const next = event.relatedTarget;
        if (next instanceof Node && !event.currentTarget.contains(next) && !categoryControls.current?.contains(next)) {
          lastReadingFocus.current = null;
        }
      }}>
      {categoryHost && active && !compact && createPortal(categoryFilters, categoryHost)}
      <div className="catalog-browse-controls" hidden={compact && readerOpen}>
      <div className="catalog-heading">
        <div><h2>{t("catalogTitle")}</h2><p>{t("catalogIntro")}</p></div>
        <span className="catalog-total">{sources.length} {t("catalogItems")}</span>
      </div>
      <div className="catalog-organize" role="group" aria-label={t("catalogOrganize")}>
        {organizationViews.map(([value, label]) => <button key={value} type="button" className="button secondary"
          aria-pressed={organization === value} onClick={() => setOrganization(value)}>
          {t(label)} ({sources.filter((record) => matchesOrganization(record, value)).length})
        </button>)}
      </div>
      <div className="catalog-toolbar">
        <label className="catalog-search">{t("catalogSearch")}
          <input ref={searchInput} type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("catalogSearchHint")} />
        </label>
        <label className="catalog-category-select">{t("catalogCategory")}
          <select ref={categorySelect} aria-label={t("catalogCategory")} value={selectedCategory} onChange={(event) => setSelectedCategory(event.target.value)}>
            <option value="">{t("catalogAllCategories")}</option>
            {categories.map((value) => <option key={value} value={value}>{categoryName(value, t)} ({sources.filter((record) => category(record) === value).length})</option>)}
          </select>
        </label>
        <p className="catalog-match" role="status">{visible.length} / {sources.length} {t("catalogItems")}</p>
        {(query || selectedCategory || organization !== "all") && <button type="button" className="button text-button small"
          onClick={() => {setQuery(""); setSelectedCategory(""); setOrganization("all"); searchInput.current?.focus();}}>{t("catalogClearFilters")}</button>}
      </div>
      {selectionMissing && <p role="status">{t("catalogSelectionMissing")}</p>}
      </div>
      <div className="catalog-workspace">
        {!categoryHost && categoryFilters}
        <div className="catalog-list" ref={list} hidden={compact && readerOpen}>
          {visible.length ? (
            <table>
              <thead><tr><th scope="col">{t("title")}</th><th scope="col">{t("catalogYear")}</th><th scope="col">{t("catalogCategory")}</th><th scope="col">{t("catalogCoverage")}</th></tr></thead>
              <tbody>{visible.map((record, index) => {
                const authors = formatAuthors(record.data.authors);
                const venue = text(record.data.venue) || text(record.data.journal);
                const decision = screenedDecision(record);
                return (
                <tr key={record.id} className={selected?.id === record.id ? "is-selected" : undefined}>
                  <td><button ref={selected?.id === record.id ? selectedButton : undefined} className="catalog-title" aria-controls={detailId} aria-describedby={registeredDrafts.has(record.id) ? `${detailId}-draft-${index}` : undefined} aria-pressed={selected?.id === record.id} onClick={() => {
                    returnPosition.current = {page: window.scrollY, list: list.current?.scrollTop ?? 0};
                    setSelectionMissing(false); setReaderOpen(true); openDraftRequested.current = true;
                    if (selectedId === record.id && readerOpen) { detailHeading.current?.focus(); openDrafts(false); openDraftRequested.current = false; }
                    else { focusRequested.current = true; setSelectedId(record.id); }
                  }}>{text(record.data.title)}</button>
                    {(authors || venue || record.kind === "library-note" || matches?.get(record.id)?.length) && (
                      <span className="catalog-submeta">
                        {[authors, venue, record.kind === "library-note" ? t("libraryNoteOrigin") : null, matches?.get(record.id)?.length ? t("libraryIdentityMatch") : null].filter(Boolean).join(" · ")}
                      </span>
                    )}
                    {registeredDrafts.has(record.id) && <span id={`${detailId}-draft-${index}`} className="catalog-draft-tag">{t("catalogDraftRegistered")}</span>}</td>
                  <td>{text(record.data.year) || "—"}</td>
                  <td><span className="badge neutral catalog-category">{categoryName(category(record), t)}</span></td>
                  <td>
                    <span className="badge neutral">{readingScope(record, t)}</span>
                    {record.kind === "source" && (
                      decision === "include" ? <span className="badge good catalog-item-state">✓ {t("include")}</span>
                        : decision === "exclude" ? <span className="badge danger catalog-item-state">✕ {t("exclude")}</span>
                          : <span className="badge warn catalog-item-state">{t("catalogNeedsScreening")}</span>
                    )}
                    {registeredNativeSummary(record) && <span className="badge good catalog-item-state">{t("catalogNativeRegistered")}</span>}
                    {missingSummary(record) && <span className="badge neutral catalog-item-state">{t("catalogNeedsSummary")}</span>}
                  </td>
                </tr>
              );})}</tbody>
            </table>
          ) : <p className="catalog-empty">{sources.length ? t("catalogNoMatches") : t("noSources")}</p>}
        </div>
        <aside id={detailId} ref={reader} className="catalog-detail" aria-label={t("catalogDetail")} hidden={compact && !readerOpen}
          onKeyDown={event => {
            if (compact && event.key === "Escape" && !(event.target as Element).closest('[role="dialog"]')) {
              event.stopPropagation(); returnRequested.current = true; setReaderOpen(false);
            }
          }}>
          {selected ? <>
            <div className="catalog-detail-top">
              <div className="catalog-meta">
                <span>{text(selected.data.year) || "—"}</span>
                <span>·</span>
                <span>{categoryName(category(selected), t)}</span>
                <span>·</span>
                <span>{readingScope(selected, t)}</span>
                <span className="badge neutral">{statusLabel(text(selected.data.identity_status) || "unverified", t)}</span>
              </div>
              <button type="button" className="button text-button small catalog-back" aria-label={t("catalogBackToList")} onClick={() => {
                if (compact) { returnRequested.current = true; setReaderOpen(false); }
                else { selectedButton.current?.focus(); }
              }}>← {t("catalogBackShort")}</button>
            </div>
            <h3 ref={detailHeading} tabIndex={-1}>{text(selected.data.title)}</h3>
            {(selectedAuthors || selectedVenue || selected.data.locator_kind !== "local-copy") && (
              <p className="catalog-authors-line">
                {[selectedAuthors, selectedVenue].filter(Boolean).join(" · ")}
                {(selectedAuthors || selectedVenue) && selected.data.locator_kind !== "local-copy" && selected.data.locator ? " · " : ""}
                {selected.data.locator_kind !== "local-copy" && <SourceLink locator={selected.data.locator} title={t("catalogOriginalSource")} />}
              </p>
            )}
            {note && <p className="catalog-missing">{t("libraryReadOnly")}</p>}
            {!note && <div className="catalog-triage-bar">
              <details className="catalog-screening">
                <summary>
                  <span>{t("catalogScreening")}</span>
                  <span className={`badge ${selectedDecision === "include" ? "good" : selectedDecision === "exclude" ? "danger" : "warn"}`}>
                    {selectedDecision === "include" ? `✓ ${t("include")}` : selectedDecision === "exclude" ? `✕ ${t("exclude")}` : t("catalogNeedsScreening")}
                  </span>
                </summary>
                <p className="small muted">{t("catalogScreeningHelp")}</p>
                {latest && <div className="catalog-saved-screening" role="status"><strong>{statusLabel(text(latest.data.decision), t)}</strong><ReadText value={text(latest.data.rationale)} /></div>}
                <MutationForm key={selected.id} t={t} submit={t("catalogSaveScreening")} fields={[
                  {name:"decision",label:t("decision"),options:[{value:"include",label:t("include")},{value:"exclude",label:t("exclude")}]},
                  {name:"rationale",label:t("rationale"),textarea:true},
                ]} onSubmit={(data) => onScreen(selected.id, String(data.get("decision")), String(data.get("rationale")))} />
              </details>
            </div>}
            {!note && registeredNativeSummary(selected) && (
              <NativeSummaryReader record={selected} scope={draftScope ? {...draftScope, active: draftScope.active && (!compact || readerOpen)} : undefined} t={t} exportable />
            )}
            <section>
              <h4>{note ? t("librarySavedAbstract") : t("catalogSavedSummary")}</h4>
              {summary ? <ReadText value={summary} /> : <p className="catalog-missing">{t(registeredNativeSummary(selected) ? "catalogNoSeparateSummary" : "catalogNoSummary")}</p>}
            </section>
            <SavedWorkingSummary record={selected} t={t}/>
            {registeredDrafts.has(selected.id) && <div className="catalog-draft-entry"><p className="small">{t("catalogDraftHelp")}</p>
              <button type="button" className="button secondary small" onClick={() => openDrafts()}>{t("catalogOpenDrafts")}</button></div>}
            {!note && <div ref={observationReader}>{observationText ? <SourceObservations record={selected} context={observationText} t={t} /> :
              <ObservationPreview record={selected} scope={observationRead ? {...observationRead, active: observationRead.active && (!compact || readerOpen)} : undefined} t={t} />}</div>}
            {!note && <WorkingSummaryEditor record={selected} scope={draftScope ? {...draftScope, active:draftScope.active && (!compact || readerOpen)} : undefined}
              suspended={Boolean(pageSuspended && draftScope?.active === false && (!compact || readerOpen))}
              onOpen={() => {setSelectedId(selected.id); setReaderOpen(true);}}
              t={t} onSaved={onWorkingSummarySaved}/>}
            <section><h4>{t("catalogRelevance")}</h4>{text(selected.data.relevance) ? <ReadText value={text(selected.data.relevance)} /> : <p className="small muted">{t("catalogNoRelevance")}</p>}</section>
            <section aria-label={t("catalogOrganizationState")}>
              <h4>{t("catalogOrganizationState")}</h4>
              <ul className="catalog-state-pills">
                {!category(selected) && <li className="badge warn">{t("catalogNeedsCategory")}</li>}
                {registeredNativeSummary(selected) && <li className="badge good">{t("catalogNativeRegistered")}</li>}
                {missingSummary(selected) && <li className="badge neutral">{t("catalogNeedsSummary")}</li>}
                <li className="badge neutral">{note ? t("catalogReadOnlyItem") : screened(selected) ? t("catalogScreeningRecorded") : t("catalogNeedsScreening")}</li>
              </ul>
            </section>
            <section><h4>{t("catalogSource")}</h4>
              <p className="small muted">{text(selected.data.reading_level_note) || t("catalogScopeHelp")}</p>
              {selected.data.locator_kind === "local-copy" && <p className="small">{t("intakeLocalLocator")}</p>}
              {text(selected.data.doi) && <p className="small">DOI: {text(selected.data.doi)}</p>}
              {note && <><p className="small">{t("libraryNotePath")}: <code>{text(selected.data.note_path)}</code></p><p className="small">{t("libraryMetadataStatus")}: {selected.data.metadata_status === "available" ? t("libraryAvailable") : t("libraryUnavailableMetadata")}</p>{text(selected.data.saved_reading_status) && <p className="small">{t("librarySavedStatus")}: {text(selected.data.saved_reading_status)}</p>}</>}
              {Boolean(matches?.get(selected.id)?.length) && <div className="catalog-missing"><strong>{t("libraryIdentityMatch")}</strong><p>{t("libraryMatchHelp")}</p><ul>{matches!.get(selected.id)!.map((other) => <li key={other.id}>{text(other.data.title)} · {other.kind === "library-note" ? t("libraryNoteOrigin") : t("libraryWorkspaceOrigin")}{other.kind === "library-note" && <><br /><code>{text(other.data.note_path)}</code></>}</li>)}</ul></div>}
              {text(selected.data.publication_version) && <p className="small">{text(selected.data.publication_version)}</p>}
              <details className="catalog-provenance"><summary>{t("catalogProvenance")}</summary><p>{note ? t("libraryNoteOrigin") : text(selected.data.batch_id) || t("catalogUnknownOrigin")}</p>{Array.isArray(selected.data.prior_batch_matches) && selected.data.prior_batch_matches.length > 0 && <p>{t("catalogPriorMatch")}</p>}</details>
            </section>
            <details className="catalog-tool-use"><summary>{t("catalogToolUse")}</summary><dl>
              <dt>Zotero</dt><dd>{(() => {
                const probe = liveIntegrations?.zotero;
                if (probe) {
                  return t(
                    probe.status === "connected_local_and_web"
                      ? "integrationZoteroConnectedBoth"
                      : probe.status === "connected_web"
                        ? "integrationZoteroConnectedWeb"
                        : probe.status === "connected_local"
                          ? "integrationZoteroConnectedLocal"
                          : probe.status === "auth_failed"
                            ? "integrationZoteroAuthFailed"
                            : probe.status === "missing_credentials"
                              ? "integrationZoteroMissingCreds"
                              : "integrationZoteroUnreachable",
                  );
                }
                const localCap = liveIntegrations?.credentials ?? workspace?.capabilities?.local_integrations;
                return t(localCap?.zotero_configured ? "catalogZoteroConfigured" : "catalogZoteroUnavailable");
              })()}</dd>
              <dt>Obsidian</dt><dd>{(() => {
                if (note) return t("catalogObsidianReadOnly");
                if (liveIntegrations?.obsidian) {
                  return obsidianStatusLabel(liveIntegrations.obsidian, t);
                }
                return t(
                  workspace?.capabilities?.obsidian_validation?.status === "available"
                    ? "catalogObsidianConfigured"
                    : "catalogObsidianUnavailable",
                );
              })()}</dd>
              <dt>NotebookLM</dt><dd>{(() => {
                const probe = liveIntegrations?.notebooklm;
                if (probe) {
                  return t(
                    probe.status === "authenticated"
                      ? "catalogNlmAuthenticated"
                      : probe.status === "expired"
                        ? "catalogNlmExpired"
                        : "catalogNlmUnavailable",
                  );
                }
                const localCap = liveIntegrations?.credentials ?? workspace?.capabilities?.local_integrations;
                return t(localCap?.nlm_state_present ? "catalogNlmStatePresent" : "catalogNlmUnavailable");
              })()}</dd>
            </dl></details>
            {!note && <button className="button secondary small catalog-source-tools" onClick={() => onPrepare(selected)}>{t("catalogSourceTools")}</button>}
          </> : <p>{t("catalogSelectSource")}</p>}
        </aside>
      </div>
    </section>
  );
}
