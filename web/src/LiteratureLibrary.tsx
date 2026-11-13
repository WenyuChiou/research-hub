import { NativeSummaryReader } from "./NativeSummaryReader";
import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useCompactReadingLayout } from "./readingLayout";
import { MutationForm, ReadText, SourceLink } from "./components";
import { statusLabel, type Translate } from "./i18n";
import type { ResearchRecord } from "./types";
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

export function LiteratureLibrary({ sources, screenings, t, onScreen, onPrepare, matches, observationText, observationRead, pageSuspended, categoryHost, onWorkingSummarySaved }: {
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
  const screened = (record: ResearchRecord) => {
    const decision = latestScreenings.get(record.id)?.data;
    return Boolean(decision && (decision.decision === "include" || decision.decision === "exclude") && typeof decision.rationale === "string" && decision.rationale.trim());
  };
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
    (!search || [record.data.title, record.data.year, record.data.relevance, category(record), ...strings(record.data.tags), ...strings(record.data.labels)]
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
    // Retain every declared version. Focus follows saved order, not a newest-
    // version selection or a preference for one observation's claims.
    if (focus) entries?.[0]?.querySelector<HTMLElement>(":scope > summary")?.focus();
  }
  const categoryFilters = <div ref={categoryControls} className="catalog-categories" role="group" aria-label={t("catalogCategories")} hidden={compact}>
    <h3>{t("catalogCategories")}</h3>
    <button type="button" aria-pressed={!selectedCategory} onClick={() => setSelectedCategory("")}>{t("catalogAllCategories")} <span>{sources.length}</span></button>
    {categories.map(value => <button type="button" key={value} aria-pressed={selectedCategory === value} onClick={() => setSelectedCategory(value)}>{categoryName(value,t)} <span>{sources.filter(record => category(record) === value).length}</span></button>)}
  </div>;

  return (
    <section className={`literature-library${compact && readerOpen ? " is-reading" : ""}`} aria-label={t("catalogTitle")}
      onFocusCapture={event => { lastReadingFocus.current = event.target as Element; }}
      onBlurCapture={event => {
        const next = event.relatedTarget;
        // Keep the pre-CSS target only until focus actually leaves this desk.
        // Category controls may live in the sidebar portal, outside this DOM node.
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
      <p className="catalog-organization-help">{t("catalogOrganizationHelp")}</p>
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
        {(query || selectedCategory || organization !== "all") && <button type="button" className="button text-button"
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
              <tbody>{visible.map((record, index) => (
                <tr key={record.id} className={selected?.id === record.id ? "is-selected" : undefined}>
                  <td><button ref={selected?.id === record.id ? selectedButton : undefined} className="catalog-title" aria-controls={detailId} aria-describedby={registeredDrafts.has(record.id) ? `${detailId}-draft-${index}` : undefined} aria-pressed={selected?.id === record.id} onClick={() => {
                    returnPosition.current = {page: window.scrollY, list: list.current?.scrollTop ?? 0};
                    setSelectionMissing(false); setReaderOpen(true); openDraftRequested.current = true;
                    if (selectedId === record.id && readerOpen) { detailHeading.current?.focus(); openDrafts(false); openDraftRequested.current = false; }
                    else { focusRequested.current = true; setSelectedId(record.id); }
                  }}>{text(record.data.title)}</button><span className="catalog-origin">{record.kind === "library-note" ? t("libraryNoteOrigin") : t("libraryWorkspaceOrigin")}{Boolean(matches?.get(record.id)?.length) && <> · {t("libraryIdentityMatch")}</>}</span>
                    {registeredDrafts.has(record.id) && <span id={`${detailId}-draft-${index}`} className="catalog-draft-tag">{t("catalogDraftRegistered")}</span>}</td>
                  <td>{text(record.data.year) || "—"}</td>
                  <td><span className="catalog-category">{categoryName(category(record), t)}</span></td>
                  <td>{readingScope(record, t)}
                    {registeredNativeSummary(record) && <span className="catalog-item-state">{t("catalogNativeRegistered")}</span>}
                    {missingSummary(record) && <span className="catalog-item-state">{t("catalogNeedsSummary")}</span>}
                    {record.kind === "source" && !screened(record) && <span className="catalog-item-state">{t("catalogNeedsScreening")}</span>}
                  </td>
                </tr>
              ))}</tbody>
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
            <p className="catalog-detail-label">{t("catalogDetail")}</p>
            <h3 ref={detailHeading} tabIndex={-1}>{text(selected.data.title)}</h3>
            <button type="button" className="button text-button catalog-back" onClick={() => {
              if (compact) { returnRequested.current = true; setReaderOpen(false); }
              else { selectedButton.current?.focus(); }
            }}>{t("catalogBackToList")}</button>
            <div className="catalog-meta"><span>{text(selected.data.year) || "—"}</span><span>{categoryName(category(selected), t)}</span><span>{statusLabel(text(selected.data.identity_status) || "unverified", t)}</span><span>{readingScope(selected,t)}</span></div>
            {selected.data.locator_kind !== "local-copy" && <SourceLink locator={selected.data.locator} title={t("catalogOriginalSource")} />}
            {note && <p className="catalog-missing">{t("libraryReadOnly")}</p>}
            <section><h4>{note ? t("librarySavedAbstract") : t("catalogSavedSummary")}</h4>{summary ? <ReadText value={summary} /> : <p className="catalog-missing">{t(registeredNativeSummary(selected) ? "catalogNoSeparateSummary" : "catalogNoSummary")}</p>}</section>
            <SavedWorkingSummary record={selected} t={t}/>
            {registeredDrafts.has(selected.id) && <div className="catalog-draft-entry"><p className="small">{t("catalogDraftHelp")}</p>
              <button type="button" className="button secondary" onClick={() => openDrafts()}>{t("catalogOpenDrafts")}</button></div>}
            {!note && <NativeSummaryReader record={selected} scope={draftScope ? {...draftScope, active: draftScope.active && (!compact || readerOpen)} : undefined} t={t} />}
            {!note && <div ref={observationReader}>{observationText ? <SourceObservations record={selected} context={observationText} t={t} /> :
              <ObservationPreview record={selected} scope={observationRead ? {...observationRead, active: observationRead.active && (!compact || readerOpen)} : undefined} t={t} />}</div>}
            {!note && <WorkingSummaryEditor record={selected} scope={draftScope ? {...draftScope, active:draftScope.active && (!compact || readerOpen)} : undefined}
              suspended={Boolean(pageSuspended && draftScope?.active === false && (!compact || readerOpen))}
              onOpen={() => {setSelectedId(selected.id); setReaderOpen(true);}}
              t={t} onSaved={onWorkingSummarySaved}/>}
            <section aria-label={t("catalogOrganizationState")}><h4>{t("catalogOrganizationState")}</h4><ul>
              {!category(selected) && <li>{t("catalogNeedsCategory")}</li>}
              {registeredNativeSummary(selected) && <li>{t("catalogNativeRegistered")}</li>}
              {missingSummary(selected) && <li>{t("catalogNeedsSummary")}</li>}
              <li>{note ? t("catalogReadOnlyItem") : screened(selected) ? t("catalogScreeningRecorded") : t("catalogNeedsScreening")}</li>
            </ul></section>
            <section><h4>{t("catalogCoverage")}</h4><p className="small muted">{text(selected.data.reading_level_note) || t("catalogScopeHelp")}</p></section>
            <section><h4>{t("catalogRelevance")}</h4>{text(selected.data.relevance) ? <ReadText value={text(selected.data.relevance)} /> : <p className="muted">{t("catalogNoRelevance")}</p>}</section>
            <section><h4>{t("catalogSource")}</h4>
              {selected.data.locator_kind === "local-copy" && <p>{t("intakeLocalLocator")}</p>}
              {text(selected.data.doi) && <p className="small">DOI: {text(selected.data.doi)}</p>}
              {note && <><p className="small">{t("libraryNotePath")}: <code>{text(selected.data.note_path)}</code></p><p className="small">{t("libraryMetadataStatus")}: {selected.data.metadata_status === "available" ? t("libraryAvailable") : t("libraryUnavailableMetadata")}</p>{text(selected.data.saved_reading_status) && <p className="small">{t("librarySavedStatus")}: {text(selected.data.saved_reading_status)}</p>}</>}
              {Boolean(matches?.get(selected.id)?.length) && <div className="catalog-missing"><strong>{t("libraryIdentityMatch")}</strong><p>{t("libraryMatchHelp")}</p><ul>{matches!.get(selected.id)!.map((other) => <li key={other.id}>{text(other.data.title)} · {other.kind === "library-note" ? t("libraryNoteOrigin") : t("libraryWorkspaceOrigin")}<br /><code>{other.kind === "library-note" ? text(other.data.note_path) : other.id}</code></li>)}</ul></div>}
              {text(selected.data.publication_version) && <p className="small">{text(selected.data.publication_version)}</p>}
              <details className="catalog-provenance"><summary>{t("catalogProvenance")}</summary><p>{note ? t("libraryNoteOrigin") : text(selected.data.batch_id) || t("catalogUnknownOrigin")}</p>{note && <p className="small">{t("libraryMetadataHash")}: <code>{text(selected.data.frontmatter_sha256) || t("libraryUnavailableMetadata")}</code></p>}{Array.isArray(selected.data.prior_batch_matches) && selected.data.prior_batch_matches.length > 0 && <p>{t("catalogPriorMatch")}</p>}</details>
            </section>
            <details className="catalog-tool-use"><summary>{t("catalogToolUse")}</summary><dl>
              <dt>Zotero</dt><dd>{t("catalogZoteroUnavailable")}</dd>
              <dt>Obsidian</dt><dd>{t(note ? "catalogObsidianReadOnly" : "catalogObsidianUnavailable")}</dd>
              <dt>NotebookLM</dt><dd>{t("catalogNlmUnavailable")}</dd>
            </dl></details>
            {!note && <details className="catalog-screening">
              <summary>{t("catalogScreening")}</summary>
              <p className="small muted">{t("catalogScreeningHelp")}</p>
              {latest && <div className="catalog-saved-screening" role="status"><strong>{statusLabel(text(latest.data.decision), t)}</strong><ReadText value={text(latest.data.rationale)} /></div>}
              <MutationForm key={selected.id} t={t} submit={t("catalogSaveScreening")} fields={[
                {name:"decision",label:t("decision"),options:[{value:"include",label:t("include")},{value:"exclude",label:t("exclude")}]},
                {name:"rationale",label:t("rationale"),textarea:true},
              ]} onSubmit={(data) => onScreen(selected.id, String(data.get("decision")), String(data.get("rationale")))} />
            </details>}
            {!note && <button className="button secondary catalog-source-tools" onClick={() => onPrepare(selected)}>{t("catalogSourceTools")}</button>}
          </> : <p>{t("catalogSelectSource")}</p>}
        </aside>
      </div>
    </section>
  );
}
