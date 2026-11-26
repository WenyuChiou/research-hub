import { NativeSummaryReader } from "./NativeSummaryReader";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { safeSourceUrl } from "./api";
import { useCompactReadingLayout } from "./readingLayout";
import { MutationForm, ReadText, SourceLink, ErrorMessage } from "./components";
import { obsidianStatusLabel, statusLabel, type Translate } from "./i18n";
import type { IntegrationLiveState, ResearchRecord, Workspace } from "./types";
import { SourceObservations } from "./ObservationHistory";
import type { ObservationTextContext } from "./sourceObservations";
import { ObservationPreview, observationArtifacts, type ObservationReadScope } from "./ObservationPreview";
import { SavedWorkingSummary, WorkingSummaryEditor, workingSummary } from "./WorkingSummaryEditor";

const text = (value: unknown) => typeof value === "string" || typeof value === "number" ? String(value) : "";
export const sourceCategory = (record: ResearchRecord) => text(record.data.category).trim() || text(record.data.sub_category).trim();
const category = sourceCategory;
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
type ViewMode = "split" | "table";
type SortKey = "default" | "year-desc" | "year-asc" | "title-asc" | "category-asc";

export interface CategorySummaryGroup {
  key: string;
  isUnclassified: boolean;
  total: number;
  included: number;
  excluded: number;
  awaiting: number;
  withSummary: number;
}

export interface LiteratureSummaryStats {
  total: number;
  categorized: number;
  included: number;
  excluded: number;
  awaiting: number;
  withSummary: number;
  groups: CategorySummaryGroup[];
}

export function latestScreeningMap(screenings: ResearchRecord[]): Map<string, ResearchRecord> {
  const map = new Map<string, ResearchRecord>();
  for (const screening of screenings) {
    if (screening.kind === "screening" && typeof screening.data.source_id === "string") {
      map.set(screening.data.source_id, screening);
    }
  }
  return map;
}

export function screeningDecisionFor(record: ResearchRecord, latest: Map<string, ResearchRecord>): "include" | "exclude" | null {
  const decision = latest.get(record.id)?.data;
  if (decision && (decision.decision === "include" || decision.decision === "exclude") && typeof decision.rationale === "string" && decision.rationale.trim()) {
    return decision.decision;
  }
  return null;
}

export function buildLiteratureSummaryStats(sources: ResearchRecord[], screenings: ResearchRecord[]): LiteratureSummaryStats {
  const latest = latestScreeningMap(screenings);
  const byKey = new Map<string, CategorySummaryGroup>();
  let categorized = 0;
  let included = 0;
  let excluded = 0;
  let awaiting = 0;
  let withSummary = 0;
  for (const record of sources) {
    const cat = sourceCategory(record);
    const key = cat || "__unclassified__";
    const isUnclassified = !cat;
    if (!isUnclassified) categorized++;
    const decision = screeningDecisionFor(record, latest);
    const hasSummary = !missingSummary(record);
    if (decision === "include") included++;
    else if (decision === "exclude") excluded++;
    else if (record.kind === "source") awaiting++;
    if (hasSummary) withSummary++;
    let group = byKey.get(key);
    if (!group) {
      group = { key, isUnclassified, total: 0, included: 0, excluded: 0, awaiting: 0, withSummary: 0 };
      byKey.set(key, group);
    }
    group.total++;
    if (decision === "include") group.included++;
    else if (decision === "exclude") group.excluded++;
    else if (record.kind === "source") group.awaiting++;
    if (hasSummary) group.withSummary++;
  }
  const groups = [...byKey.values()].sort((a, b) => {
    if (a.isUnclassified !== b.isUnclassified) return a.isUnclassified ? 1 : -1;
    if (b.total !== a.total) return b.total - a.total;
    return a.key.localeCompare(b.key);
  });
  return { total: sources.length, categorized, included, excluded, awaiting, withSummary, groups };
}

function escapeMarkdownCell(value: string): string {
  return value.replace(/\r?\n/g, " ").replace(/\|/g, "\\|").trim() || "—";
}

function escapeCsvCell(value: string): string {
  const cleaned = value.replace(/\r?\n/g, " ").trim();
  const safe = /^[=+\-@\t\r]/.test(cleaned) ? `'${cleaned}` : cleaned;
  return `"${safe.replace(/"/g, '""')}"`;
}

function numericYear(value: unknown): number {
  const parsed = Number.parseInt(text(value), 10);
  return Number.isFinite(parsed) ? parsed : -Infinity;
}

function authorNames(value: unknown): string[] {
  if (typeof value === "string") {
    return value.trim() ? [value.trim()] : [];
  }
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
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
}

function formatAuthors(value: unknown): string {
  const names = authorNames(value);
  if (!names.length) return "";
  return names.length > 2 ? `${names[0]} et al.` : names.join(", ");
}

export function categoryName(value: string, t: Translate) {
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

export interface SourceCurationInput {
  category?: string;
  year?: string;
  authors?: string[];
  venue?: string;
  relevance?: string;
  summary?: string;
}

const CURATION_KEYS = ["category", "year", "authors", "venue", "relevance", "summary", "tags"] as const;

export function applySourceCurations(
  sources: ResearchRecord[],
  curations?: ResearchRecord[],
): ResearchRecord[] {
  if (!curations?.length) return sources;
  const overlays = new Map<string, Record<string, unknown>>();
  for (const record of curations) {
    if (record.kind !== "source_curation" || typeof record.data.source_id !== "string") continue;
    const current = overlays.get(record.data.source_id) ?? {};
    for (const key of CURATION_KEYS) {
      if (key in record.data) current[key] = record.data[key];
    }
    overlays.set(record.data.source_id, current);
  }
  if (!overlays.size) return sources;
  return sources.map((record) => {
    if (record.kind !== "source") return record;
    const overlay = overlays.get(record.id);
    if (!overlay) return record;
    const nextData: Record<string, unknown> = { ...record.data, ...overlay };
    if ("summary" in overlay && !text(overlay.summary).trim()) {
      nextData.abstract = "";
    }
    if ("venue" in overlay && !text(overlay.venue).trim()) {
      nextData.journal = "";
    }
    return { ...record, data: nextData };
  });
}

function formatAuthorsInput(value: unknown): string {
  const names = authorNames(value);
  return names.some((name) => /[,，]/.test(name)) ? names.join("; ") : names.join(", ");
}

function parseAuthorsInput(value: string): string[] {
  const delimiter = /[;；\n]/.test(value) ? /[;；\n]+/ : /[,，]+/;
  return value
    .split(delimiter)
    .map((item) => item.trim())
    .filter(Boolean);
}

interface CurationDraft {
  category: string;
  year: string;
  authors: string;
  venue: string;
  relevance: string;
  summary: string;
  changed: {
    category?: boolean;
    year?: boolean;
    authors?: boolean;
    venue?: boolean;
    relevance?: boolean;
    summary?: boolean;
  };
}

function baseCurationDraft(record: ResearchRecord): CurationDraft {
  return {
    category: sourceCategory(record),
    year: text(record.data.year),
    authors: formatAuthorsInput(record.data.authors),
    venue: text(record.data.venue) || text(record.data.journal),
    relevance: text(record.data.relevance),
    summary: savedSummary(record),
    changed: {},
  };
}

function isDraftDirty(draft: CurationDraft | undefined): boolean {
  return Boolean(draft && Object.values(draft.changed).some(Boolean));
}

function SourceCurationForm({
  draft,
  dirty,
  saved,
  categories,
  t,
  onChange,
  onDiscard,
  onSave,
}: {
  draft: CurationDraft;
  dirty: boolean;
  saved: boolean;
  categories: string[];
  t: Translate;
  onChange: (next: CurationDraft) => void;
  onDiscard: () => void;
  onSave: (curation: SourceCurationInput) => Promise<void>;
}) {
  const listId = useId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const suggestions = [...new Set(["llm", "human", "human-review", ...categories])];

  return (
    <form
      className="record-form catalog-curation-form"
      aria-busy={busy}
      onSubmit={async (event) => {
        event.preventDefault();
        const payload: SourceCurationInput = {};
        if (draft.changed.category) payload.category = draft.category.trim();
        if (draft.changed.year) payload.year = draft.year.trim();
        if (draft.changed.authors) payload.authors = parseAuthorsInput(draft.authors);
        if (draft.changed.venue) payload.venue = draft.venue.trim();
        if (draft.changed.relevance) payload.relevance = draft.relevance.trim();
        if (draft.changed.summary) payload.summary = draft.summary.trim();
        if (!Object.keys(payload).length) return;
        setBusy(true);
        setError(null);
        try {
          await onSave(payload);
        } catch (failure) {
          setError(failure);
        } finally {
          setBusy(false);
        }
      }}
    >
      <fieldset disabled={busy}>
        <div className="form-grid">
          <div className="field">
            <label htmlFor={`${listId}-cat`}>{t("catalogCategory")}</label>
            <input
              id={`${listId}-cat`}
              list={listId}
              value={draft.category}
              onChange={(e) => onChange({ ...draft, category: e.target.value, changed: { ...draft.changed, category: true } })}
              maxLength={120}
            />
            <datalist id={listId}>
              {suggestions.map((item) => (
                <option key={item} value={item} />
              ))}
            </datalist>
            <small>{t("catalogMetaCategoryHint")}</small>
          </div>
          <div className="field">
            <label htmlFor={`${listId}-year`}>{t("catalogYear")}</label>
            <input
              id={`${listId}-year`}
              value={draft.year}
              onChange={(e) => onChange({ ...draft, year: e.target.value, changed: { ...draft.changed, year: true } })}
              pattern="[0-9]{4}"
              maxLength={4}
              placeholder="2024"
            />
            <small>{t("catalogMetaYearHint")}</small>
          </div>
          <div className="field field-wide">
            <label htmlFor={`${listId}-authors`}>{t("catalogMetaAuthors")}</label>
            <input
              id={`${listId}-authors`}
              value={draft.authors}
              onChange={(e) => onChange({ ...draft, authors: e.target.value, changed: { ...draft.changed, authors: true } })}
              maxLength={1000}
            />
            <small>{t("catalogMetaAuthorsHint")}</small>
          </div>
          <div className="field field-wide">
            <label htmlFor={`${listId}-venue`}>{t("catalogMetaVenue")}</label>
            <input
              id={`${listId}-venue`}
              value={draft.venue}
              onChange={(e) => onChange({ ...draft, venue: e.target.value, changed: { ...draft.changed, venue: true } })}
              maxLength={300}
            />
          </div>
          <div className="field field-wide">
            <label htmlFor={`${listId}-rel`}>{t("catalogRelevance")}</label>
            <textarea
              id={`${listId}-rel`}
              rows={2}
              value={draft.relevance}
              onChange={(e) => onChange({ ...draft, relevance: e.target.value, changed: { ...draft.changed, relevance: true } })}
              maxLength={4000}
            />
          </div>
          <div className="field field-wide">
            <label htmlFor={`${listId}-sum`}>{t("catalogMetaSummary")}</label>
            <textarea
              id={`${listId}-sum`}
              rows={3}
              value={draft.summary}
              onChange={(e) => onChange({ ...draft, summary: e.target.value, changed: { ...draft.changed, summary: true } })}
              maxLength={20000}
            />
          </div>
        </div>
        <div className="catalog-curation-actions">
          <button className="button primary" type="submit">
            {busy ? t("saving") : t("catalogSaveMeta")}
          </button>
          {dirty && (
            <button
              className="button secondary small"
              type="button"
              onClick={() => {
                setError(null);
                onDiscard();
              }}
            >
              {t("catalogResetMeta")}
            </button>
          )}
        </div>
      </fieldset>
      {error !== null && <ErrorMessage error={error} t={t} />}
      {saved && (
        <p role="status" className="saved-note">
          ✓ {t("saved")}
        </p>
      )}
    </form>
  );
}

export function LiteratureLibrary({ sources: rawSources, screenings, curations, t, onScreen, onCurate, onPrepare, onOpenAddTools, matches, observationText, observationRead, pageSuspended, categoryHost, onWorkingSummarySaved, workspace, liveIntegrations, requestedView }: {
  sources: ResearchRecord[];
  screenings: ResearchRecord[];
  curations?: ResearchRecord[];
  t: Translate;
  onScreen: (sourceId: string, decision: string, rationale: string) => Promise<void>;
  onCurate?: (sourceId: string, curation: SourceCurationInput) => Promise<void>;
  onPrepare: (record: ResearchRecord) => void;
  onOpenAddTools?: () => void;
  matches?: Map<string, ResearchRecord[]>;
  observationText?: ObservationTextContext;
  observationRead?: ObservationReadScope;
  pageSuspended?: boolean;
  categoryHost?: HTMLElement | null;
  onWorkingSummarySaved?: () => Promise<void>;
  workspace?: Workspace | null;
  liveIntegrations?: IntegrationLiveState;
  requestedView?: { mode: ViewMode; category?: string; nonce: number };
}) {
  const rawSourceById = new Map(rawSources.map((record) => [record.id, record]));
  const sources = applySourceCurations(rawSources, curations);
  const [query, setQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("");
  const [organization, setOrganization] = useState<Organization>("all");
  const [viewMode, setViewMode] = useState<ViewMode>("split");
  const [sortBy, setSortBy] = useState<SortKey>("default");
  const [exportNotice, setExportNotice] = useState<{ tone: "good" | "bad"; text: string } | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [curationOpen, setCurationOpen] = useState(false);
  const [curationDrafts, setCurationDrafts] = useState<Record<string, CurationDraft>>({});
  const [curationSavedId, setCurationSavedId] = useState<string | null>(null);
  const [openSummaryIds, setOpenSummaryIds] = useState<string[]>([]);
  const [readerOpen, setReaderOpen] = useState(false);
  const [selectionMissing, setSelectionMissing] = useState(false);
  const handleSummarySessionChange = useCallback((open: boolean, sourceRecordId: string) => {
    setOpenSummaryIds((prev) => {
      const has = prev.includes(sourceRecordId);
      if (open) return has ? prev : [...prev, sourceRecordId];
      return has ? prev.filter((id) => id !== sourceRecordId) : prev;
    });
  }, []);
  const handledRequestNonce = useRef(0);
  useEffect(() => {
    if (!requestedView || requestedView.nonce <= handledRequestNonce.current) return;
    handledRequestNonce.current = requestedView.nonce;
    setViewMode(requestedView.mode);
    setQuery("");
    if (requestedView.category === "__unclassified__") {
      setSelectedCategory("");
      setOrganization("unclassified");
    } else if (typeof requestedView.category === "string") {
      setSelectedCategory(requestedView.category);
      setOrganization("all");
    }
  }, [requestedView]);
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
    if (focusRequested.current && viewMode === "split") {
      focusRequested.current = false;
      detailHeading.current?.focus();
      if (openDraftRequested.current) { openDraftRequested.current = false; openDrafts(false); }
    }
  }, [selectedId, readerOpen, viewMode]);
  const latestScreenings = latestScreeningMap(screenings);
  const screenedDecision = (record: ResearchRecord): "include" | "exclude" | null =>
    screeningDecisionFor(record, latestScreenings);
  const screened = (record: ResearchRecord) => screenedDecision(record) !== null;
  const summaryStats = buildLiteratureSummaryStats(sources, screenings);
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
    (!search || [record.data.title, ...authorNames(record.data.authors), record.data.year, record.data.doi, record.data.venue, record.data.journal, record.data.relevance, category(record), ...strings(record.data.tags), ...strings(record.data.labels)]
      .map(text).join(" ").toLocaleLowerCase().includes(search)),
  );
  const exactSelected = visible.find((record) => record.id === selectedId);
  const selected = compact && readerOpen ? exactSelected : exactSelected ?? visible[0];
  const openSummaryRecords = openSummaryIds
    .map((id) => sources.find((record) => record.id === id))
    .filter((record): record is ResearchRecord => Boolean(record && record.kind !== "library-note"));
  const hiddenDraftRecords = openSummaryRecords.filter((record) => record.id !== selected?.id);
  const bannerDraftRecords = viewMode === "table" || (compact && !readerOpen) ? openSummaryRecords : hiddenDraftRecords;
  const editorRecords: ResearchRecord[] = [];
  if (selected && selected.kind !== "library-note") editorRecords.push(selected);
  for (const draftRecord of hiddenDraftRecords) editorRecords.push(draftRecord);
  useEffect(() => {
    if (compact && readerOpen && viewMode === "split" && !exactSelected) {
      setSelectionMissing(true); returnRequested.current = true; setReaderOpen(false);
    }
  }, [compact, readerOpen, viewMode, exactSelected]);
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
  const sortedVisible = sortBy === "default" ? visible : [...visible].sort((a, b) => {
    if (sortBy === "year-desc") {
      const ay = numericYear(a.data.year);
      const by = numericYear(b.data.year);
      if (ay === -Infinity && by === -Infinity) return 0;
      if (ay === -Infinity) return 1;
      if (by === -Infinity) return -1;
      return by - ay;
    }
    if (sortBy === "year-asc") {
      const ay = numericYear(a.data.year);
      const by = numericYear(b.data.year);
      if (ay === -Infinity && by === -Infinity) return 0;
      if (ay === -Infinity) return 1;
      if (by === -Infinity) return -1;
      return ay - by;
    }
    if (sortBy === "category-asc") {
      const ac = categoryName(category(a), t);
      const bc = categoryName(category(b), t);
      return ac.localeCompare(bc) || text(a.data.title).localeCompare(text(b.data.title));
    }
    return text(a.data.title).localeCompare(text(b.data.title));
  });

  function screeningLabelText(record: ResearchRecord): string {
    if (record.kind !== "source") return t("catalogReadOnlyItem");
    const decision = screenedDecision(record);
    if (decision === "include") return t("include");
    if (decision === "exclude") return t("exclude");
    return t("catalogNeedsScreening");
  }

  function summaryLabelText(record: ResearchRecord): string {
    if (registeredNativeSummary(record)) return t("catalogNativeRegistered");
    if (!missingSummary(record)) return t("catalogTableHasSummary");
    return t("catalogNeedsSummary");
  }

  function buildMarkdownTable(): string {
    const header = [
      t("title"),
      t("catalogCategory"),
      t("catalogYear"),
      t("catalogCoverage"),
      t("catalogTableScreening"),
      t("catalogTableSummary"),
      t("catalogTableLink"),
    ];
    const lines = [
      `| ${header.map(escapeMarkdownCell).join(" | ")} |`,
      `| ${header.map(() => "---").join(" | ")} |`,
    ];
    for (const record of sortedVisible) {
      const authors = formatAuthors(record.data.authors);
      const titleCell = authors ? `${text(record.data.title)} (${authors})` : text(record.data.title);
      const safeUrl = record.data.locator_kind !== "local-copy" ? safeSourceUrl(record.data.locator) : null;
      lines.push(
        `| ${[
          escapeMarkdownCell(titleCell),
          escapeMarkdownCell(categoryName(category(record), t)),
          escapeMarkdownCell(text(record.data.year) || "—"),
          escapeMarkdownCell(readingScope(record, t)),
          escapeMarkdownCell(screeningLabelText(record)),
          escapeMarkdownCell(summaryLabelText(record)),
          safeUrl ? escapeMarkdownCell(safeUrl) : "—",
        ].join(" | ")} |`,
      );
    }
    return lines.join("\n");
  }

  async function copyMasterMarkdown() {
    if (!navigator.clipboard?.writeText) {
      setExportNotice({ tone: "bad", text: t("catalogTableCopyFailed") });
      return;
    }
    try {
      await navigator.clipboard.writeText(buildMarkdownTable());
      setExportNotice({ tone: "good", text: t("catalogTableCopied") });
    } catch {
      setExportNotice({ tone: "bad", text: t("catalogTableCopyFailed") });
    }
  }

  function exportMasterCsv() {
    const header = [
      t("title"),
      t("catalogCategory"),
      t("catalogYear"),
      t("catalogCoverage"),
      t("catalogTableScreening"),
      t("catalogTableSummary"),
      "DOI",
      t("catalogTableLink"),
    ];
    const rows = [header.map(escapeCsvCell).join(",")];
    for (const record of sortedVisible) {
      const authors = formatAuthors(record.data.authors);
      const venue = text(record.data.venue) || text(record.data.journal);
      const titleText = [text(record.data.title), authors, venue].filter(Boolean).join(" — ");
      const safeUrl = record.data.locator_kind !== "local-copy" ? safeSourceUrl(record.data.locator) : null;
      rows.push(
        [
          titleText,
          categoryName(category(record), t),
          text(record.data.year),
          readingScope(record, t),
          screeningLabelText(record),
          summaryLabelText(record),
          text(record.data.doi),
          safeUrl || "",
        ].map(escapeCsvCell).join(","),
      );
    }
    const blob = new Blob(["\uFEFF" + rows.join("\r\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "literature-master-table.csv";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <section className={`literature-library${compact && readerOpen && viewMode === "split" ? " is-reading" : ""}`} aria-label={t("catalogTitle")}
      onFocusCapture={event => { lastReadingFocus.current = event.target as Element; }}
      onBlurCapture={event => {
        const next = event.relatedTarget;
        if (next instanceof Node && !event.currentTarget.contains(next) && !categoryControls.current?.contains(next)) {
          lastReadingFocus.current = null;
        }
      }}>
      {categoryHost && active && !compact && createPortal(categoryFilters, categoryHost)}
      <div className="catalog-browse-controls" hidden={compact && readerOpen && viewMode === "split"}>
      <div className="catalog-heading">
        <h2>{t("catalogTitle")}</h2>
        <div className="catalog-heading-actions">
          <span className="catalog-total">{sources.length} {t("catalogItems")}</span>
          <div className="catalog-view-switch" role="group" aria-label={t("catalogViewMode")}>
            <button
              type="button"
              aria-pressed={viewMode === "split"}
              data-tooltip={t("catalogViewSplitTip")}
              data-tooltip-pos="bottom-end"
              onClick={() => setViewMode("split")}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
                <rect x="3" y="4" width="18" height="16" rx="2" />
                <line x1="10" y1="4" x2="10" y2="20" />
              </svg>
              <span>{t("catalogViewSplit")}</span>
            </button>
            <button
              type="button"
              aria-pressed={viewMode === "table"}
              data-tooltip={t("catalogViewTableTip")}
              data-tooltip-pos="bottom-end"
              onClick={() => setViewMode("table")}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
                <rect x="3" y="4" width="18" height="16" rx="2" />
                <line x1="3" y1="10" x2="21" y2="10" />
                <line x1="3" y1="15" x2="21" y2="15" />
                <line x1="10" y1="10" x2="10" y2="20" />
              </svg>
              <span>{t("catalogViewTable")}</span>
            </button>
          </div>
        </div>
      </div>
      <div className="catalog-control-bar">
        <div className="catalog-organize" role="group" aria-label={t("catalogOrganize")}>
          {organizationViews.map(([value, label]) => <button key={value} type="button" className="button secondary"
            aria-pressed={organization === value} onClick={() => setOrganization(value)}>
            {t(label)} ({sources.filter((record) => matchesOrganization(record, value)).length})
          </button>)}
        </div>
        <div className="catalog-toolbar">
          <label className="catalog-search">
            <span className="sr-only">{t("catalogSearch")}</span>
            <svg className="catalog-search-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.5-3.5" />
            </svg>
            <input ref={searchInput} type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("catalogSearchHint")} />
          </label>
          <label className="catalog-category-select"><span className="sr-only">{t("catalogCategory")}</span>
            <select ref={categorySelect} aria-label={t("catalogCategory")} value={selectedCategory} onChange={(event) => setSelectedCategory(event.target.value)}>
              <option value="">{t("catalogAllCategories")}</option>
              {categories.map((value) => <option key={value} value={value}>{categoryName(value, t)} ({sources.filter((record) => category(record) === value).length})</option>)}
            </select>
          </label>
          <p className="catalog-match" role="status">{visible.length} / {sources.length} {t("catalogItems")}</p>
          {(query || selectedCategory || organization !== "all") && (
            <button
              type="button"
              className="button text-button small icon-btn"
              aria-label={t("catalogClearFilters")}
              data-tooltip={t("catalogClearFilters")}
              data-tooltip-pos="bottom-end"
              onClick={() => {setQuery(""); setSelectedCategory(""); setOrganization("all"); searchInput.current?.focus();}}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" aria-hidden="true" focusable="false">
                <path d="M18 6 6 18" />
                <path d="m6 6 12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>
      {selectionMissing && <p role="status">{t("catalogSelectionMissing")}</p>}
      </div>
      {bannerDraftRecords.length > 0 && (
        <div className="catalog-unsaved-drafts" role="status">
          <span>{t("catalogUnsavedDrafts")}</span>
          {bannerDraftRecords.map((draftRecord) => (
            <button
              key={draftRecord.id}
              type="button"
              className="button secondary small"
              onClick={() => {
                if (!visible.some((item) => item.id === draftRecord.id)) {
                  setQuery("");
                  setSelectedCategory("");
                  setOrganization("all");
                }
                setSelectionMissing(false);
                setSelectedId(draftRecord.id);
                setReaderOpen(true);
                focusRequested.current = true;
                setViewMode("split");
              }}
            >
              {t("catalogReturnDraft")}: {text(draftRecord.data.title)}
            </button>
          ))}
        </div>
      )}
      {viewMode === "table" && (
        <div className="catalog-master-view">
          {summaryStats.groups.length > 0 && (
            <div className="catalog-category-strip" role="group" aria-label={t("catalogTableCategorySummary")}>
              <button
                type="button"
                className="catalog-category-card"
                aria-pressed={!selectedCategory && organization !== "unclassified"}
                onClick={() => {
                  setSelectedCategory("");
                  if (organization === "unclassified") setOrganization("all");
                }}
              >
                <span className="catalog-category-card-top">
                  <strong>{t("catalogAllCategories")}</strong>
                  <span className="count">{summaryStats.total}</span>
                </span>
                <span className="catalog-category-card-meta">
                  {t("catalogTableIncluded")} {summaryStats.included} · {t("catalogTableAwaiting")} {summaryStats.awaiting}
                </span>
              </button>
              {summaryStats.groups.map((group) => {
                const pressed = group.isUnclassified
                  ? organization === "unclassified" && !selectedCategory
                  : selectedCategory === group.key;
                return (
                  <button
                    type="button"
                    key={group.key}
                    className="catalog-category-card"
                    aria-pressed={pressed}
                    onClick={() => {
                      if (group.isUnclassified) {
                        setSelectedCategory("");
                        setOrganization("unclassified");
                      } else {
                        setSelectedCategory(group.key);
                        if (organization === "unclassified") setOrganization("all");
                      }
                    }}
                  >
                    <span className="catalog-category-card-top">
                      <strong>{group.isUnclassified ? t("catalogUnclassified") : categoryName(group.key, t)}</strong>
                      <span className="count">{group.total}</span>
                    </span>
                    <span className="catalog-category-card-meta">
                      {t("catalogTableIncluded")} {group.included} · {t("catalogTableAwaiting")} {group.awaiting}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
          <div className="catalog-master-bar">
            <span className="catalog-master-label">{t("catalogViewTableTip")}</span>
            <div className="catalog-master-actions">
              {exportNotice && (
                <span role="status" className={exportNotice.tone === "good" ? "small good-text" : "small bad-text"}>
                  {exportNotice.text}
                </span>
              )}
              <button
                type="button"
                className="button secondary small icon-btn"
                disabled={!sortedVisible.length}
                onClick={() => void copyMasterMarkdown()}
                aria-label={t("catalogTableCopyMd")}
                data-tooltip={exportNotice?.tone === "good" ? exportNotice.text : t("catalogTableCopyMd")}
                data-tooltip-pos="bottom-end"
              >
                {exportNotice?.tone === "good" ? (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#0d6846" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
                    <path d="M20 6 9 17l-5-5" />
                  </svg>
                ) : (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
                    <rect x="9" y="9" width="13" height="13" rx="2" />
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                  </svg>
                )}
              </button>
              <button
                type="button"
                className="button secondary small icon-btn"
                disabled={!sortedVisible.length}
                onClick={exportMasterCsv}
                aria-label={t("catalogTableExportCsv")}
                data-tooltip={t("catalogTableExportCsv")}
                data-tooltip-pos="bottom-end"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="7 10 12 15 17 10" />
                  <line x1="12" y1="15" x2="12" y2="3" />
                </svg>
              </button>
            </div>
          </div>
          {sortedVisible.length ? (
            <div className="catalog-master-wrap">
              <table className="catalog-master-table">
                <thead>
                  <tr>
                    <th scope="col">
                      <button
                        type="button"
                        className="catalog-master-sort"
                        aria-pressed={sortBy === "title-asc"}
                        onClick={() => setSortBy(sortBy === "title-asc" ? "default" : "title-asc")}
                      >
                        {t("title")} {sortBy === "title-asc" ? "↑" : ""}
                      </button>
                    </th>
                    <th scope="col">
                      <button
                        type="button"
                        className="catalog-master-sort"
                        aria-pressed={sortBy === "category-asc"}
                        onClick={() => setSortBy(sortBy === "category-asc" ? "default" : "category-asc")}
                      >
                        {t("catalogCategory")} {sortBy === "category-asc" ? "↑" : ""}
                      </button>
                    </th>
                    <th scope="col">
                      <button
                        type="button"
                        className="catalog-master-sort"
                        aria-pressed={sortBy === "year-desc" || sortBy === "year-asc"}
                        onClick={() => setSortBy(sortBy === "year-desc" ? "year-asc" : "year-desc")}
                      >
                        {t("catalogYear")} {sortBy === "year-desc" ? "↓" : sortBy === "year-asc" ? "↑" : ""}
                      </button>
                    </th>
                    <th scope="col">{t("catalogCoverage")}</th>
                    <th scope="col">{t("catalogTableScreening")}</th>
                    <th scope="col">{t("catalogTableSummary")}</th>
                    <th scope="col">{t("catalogTableLink")}</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedVisible.map((record) => {
                    const authors = formatAuthors(record.data.authors);
                    const venue = text(record.data.venue) || text(record.data.journal);
                    const decision = screenedDecision(record);
                    const safeUrl = record.data.locator_kind !== "local-copy" ? safeSourceUrl(record.data.locator) : null;
                    return (
                      <tr key={record.id} className={selected?.id === record.id ? "is-selected" : undefined}>
                        <td>
                          <button
                            type="button"
                            className="catalog-master-title"
                            data-tooltip={t("catalogTableOpenPaper")}
                            data-tooltip-pos="top-start"
                            onClick={() => {
                              setSelectionMissing(false);
                              setSelectedId(record.id);
                              setReaderOpen(true);
                              focusRequested.current = true;
                              setViewMode("split");
                            }}
                          >
                            {text(record.data.title)}
                          </button>
                          {Boolean(authors || venue || record.kind === "library-note") && (
                            <span className="catalog-submeta">
                              {[authors, venue, record.kind === "library-note" ? t("libraryNoteOrigin") : null].filter(Boolean).join(" · ")}
                            </span>
                          )}
                        </td>
                        <td>
                          <span className="catalog-cat-pill">{categoryName(category(record), t)}</span>
                        </td>
                        <td className="catalog-master-year">{text(record.data.year) || "—"}</td>
                        <td><span className="catalog-meta-text">{readingScope(record, t)}</span></td>
                        <td>
                          {record.kind === "source" ? (
                            decision === "include" ? <span className="badge good">✓ {t("include")}</span>
                              : decision === "exclude" ? <span className="badge danger">✕ {t("exclude")}</span>
                                : <span className="badge warn">{t("catalogNeedsScreening")}</span>
                          ) : (
                            <span className="badge neutral">{t("catalogReadOnlyItem")}</span>
                          )}
                        </td>
                        <td>
                          {registeredNativeSummary(record) ? (
                            <span className="catalog-indicator good">{t("catalogNativeRegistered")}</span>
                          ) : !missingSummary(record) ? (
                            <span className="catalog-indicator accent">{t("catalogTableHasSummary")}</span>
                          ) : (
                            <span className="catalog-indicator muted">{t("catalogNeedsSummary")}</span>
                          )}
                        </td>
                        <td>
                          {safeUrl ? (
                            <a
                              className="catalog-ext-link"
                              href={safeUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              aria-label={`${t("catalogOriginalSource")}: ${text(record.data.title)}`}
                              data-tooltip={t("catalogOriginalSource")}
                              data-tooltip-pos="bottom-end"
                            >
                              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
                                <path d="M15 3h6v6" />
                                <path d="M10 14 21 3" />
                                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                              </svg>
                            </a>
                          ) : (
                            <span className="muted">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="catalog-empty-state">
              <p className="catalog-empty">{sources.length ? t("catalogNoMatches") : t("noSources")}</p>
              {!sources.length && onOpenAddTools && (
                <button type="button" className="button primary" onClick={onOpenAddTools}>
                  {t("catalogAddFirstSource")}
                </button>
              )}
            </div>
          )}
        </div>
      )}
      <div className="catalog-workspace" hidden={viewMode === "table"}>
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
                    {Boolean(authors || venue || record.kind === "library-note" || matches?.get(record.id)?.length) && (
                      <span className="catalog-submeta">
                        {[authors, venue, record.kind === "library-note" ? t("libraryNoteOrigin") : null, matches?.get(record.id)?.length ? t("libraryIdentityMatch") : null].filter(Boolean).join(" · ")}
                      </span>
                    )}
                    {registeredDrafts.has(record.id) && <span id={`${detailId}-draft-${index}`} className="catalog-draft-tag">{t("catalogDraftRegistered")}</span>}</td>
                  <td>{text(record.data.year) || "—"}</td>
                  <td><span className="catalog-meta-text catalog-category">{categoryName(category(record), t)}</span></td>
                  <td>
                    <span className="catalog-meta-text catalog-scope">{readingScope(record, t)}</span>
                    {record.kind === "source" && (
                      decision === "include" ? <span className="badge good catalog-item-state">✓ {t("include")}</span>
                        : decision === "exclude" ? <span className="badge danger catalog-item-state">✕ {t("exclude")}</span>
                          : <span className="badge warn catalog-item-state">{t("catalogNeedsScreening")}</span>
                    )}
                    {registeredNativeSummary(record) && <span className="catalog-indicator good">{t("catalogNativeRegistered")}</span>}
                    {missingSummary(record) && <span className="catalog-indicator muted">{t("catalogNeedsSummary")}</span>}
                  </td>
                </tr>
              );})}</tbody>
            </table>
          ) : (
            <div className="catalog-empty-state">
              <p className="catalog-empty">{sources.length ? t("catalogNoMatches") : t("noSources")}</p>
              {!sources.length && onOpenAddTools && (
                <button type="button" className="button primary" onClick={onOpenAddTools}>
                  {t("catalogAddFirstSource")}
                </button>
              )}
            </div>
          )}
        </div>
        <aside id={detailId} ref={reader} className="catalog-detail" aria-label={t("catalogDetail")} hidden={compact && !readerOpen}
          onKeyDown={event => {
            if (compact && event.key === "Escape" && !(event.target as Element).closest('[role="dialog"]')) {
              event.stopPropagation(); returnRequested.current = true; setReaderOpen(false);
            }
          }}>
          {selected ? <div key={selected.id} className="catalog-detail-body">
            <div className="catalog-detail-top">
              <div className="catalog-meta">
                <span>{text(selected.data.year) || "—"}</span>
                <span>·</span>
                <span>{categoryName(category(selected), t)}</span>
                <span>·</span>
                <span>{readingScope(selected, t)}</span>
                <span
                  className={`badge neutral${(text(selected.data.identity_status) || "unverified") === "unverified" ? " tooltip-rich" : ""}`}
                  tabIndex={(text(selected.data.identity_status) || "unverified") === "unverified" ? 0 : undefined}
                  data-tooltip={(text(selected.data.identity_status) || "unverified") === "unverified" ? t("unverifiedTip") : undefined}
                  data-tooltip-pos={(text(selected.data.identity_status) || "unverified") === "unverified" ? "bottom-end" : undefined}
                >
                  {statusLabel(text(selected.data.identity_status) || "unverified", t)}
                </span>
              </div>
              <button
                type="button"
                className="button text-button small icon-btn catalog-back"
                aria-label={t("catalogBackToList")}
                data-tooltip={t("catalogBackToList")}
                data-tooltip-pos="bottom-end"
                onClick={() => {
                  if (compact) { returnRequested.current = true; setReaderOpen(false); }
                  else { selectedButton.current?.focus(); }
                }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
                  <path d="m15 18-6-6 6-6" />
                </svg>
              </button>
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
              {onCurate && (() => {
                const selectedDraft = curationDrafts[selected.id] ?? baseCurationDraft(selected);
                const selectedDraftDirty = isDraftDirty(curationDrafts[selected.id]);
                return (
                <details className="catalog-screening catalog-curation" open={curationOpen}>
                  <summary
                    onClick={(event) => {
                      event.preventDefault();
                      setCurationOpen((open) => !open);
                    }}
                  >
                    <span>{t("catalogEditMeta")}</span>
                    <span className="catalog-curation-badges">
                      {selectedDraftDirty && <span className="badge warn">{t("catalogMetaUnsaved")}</span>}
                      <span className="catalog-cat-pill">{categoryName(category(selected), t)}</span>
                    </span>
                  </summary>
                  {curationOpen && (
                    <>
                      <p className="small muted">{t("catalogEditMetaHelp")}</p>
                      <SourceCurationForm
                        key={selected.id}
                        draft={selectedDraft}
                        dirty={selectedDraftDirty}
                        saved={curationSavedId === selected.id && !selectedDraftDirty}
                        categories={categories}
                        t={t}
                        onChange={(next) => {
                          setCurationSavedId((current) => (current === selected.id ? null : current));
                          setCurationDrafts((prev) => ({ ...prev, [selected.id]: next }));
                        }}
                        onDiscard={() => {
                          setCurationSavedId((current) => (current === selected.id ? null : current));
                          setCurationDrafts((prev) => {
                            const { [selected.id]: _, ...rest } = prev;
                            return rest;
                          });
                        }}
                        onSave={async (payload) => {
                          await onCurate(selected.id, payload);
                          setCurationDrafts((prev) => {
                            const { [selected.id]: _, ...rest } = prev;
                            return rest;
                          });
                          setCurationSavedId(selected.id);
                        }}
                      />
                    </>
                  )}
                </details>
                );
              })()}
            </div>}
            {!note && registeredNativeSummary(selected) && (
              <NativeSummaryReader record={rawSourceById.get(selected.id) ?? selected} scope={draftScope ? {...draftScope, active: draftScope.active && viewMode === "split" && (!compact || readerOpen)} : undefined} t={t} exportable />
            )}
            <section>
              <h4>{note ? t("librarySavedAbstract") : t("catalogSavedSummary")}</h4>
              {summary ? <ReadText value={summary} /> : <p className="catalog-missing">{t(registeredNativeSummary(selected) ? "catalogNoSeparateSummary" : "catalogNoSummary")}</p>}
            </section>
            <SavedWorkingSummary record={rawSourceById.get(selected.id) ?? selected} t={t}/>
            {registeredDrafts.has(selected.id) && <div className="catalog-draft-entry"><p className="small">{t("catalogDraftHelp")}</p>
              <button type="button" className="button secondary small" onClick={() => openDrafts()}>{t("catalogOpenDrafts")}</button></div>}
            {!note && <div ref={observationReader}>{observationText ? <SourceObservations record={rawSourceById.get(selected.id) ?? selected} context={observationText} t={t} /> :
              <ObservationPreview record={rawSourceById.get(selected.id) ?? selected} scope={observationRead ? {...observationRead, active: observationRead.active && viewMode === "split" && (!compact || readerOpen)} : undefined} t={t} />}</div>}
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
            {!note && <button className="button secondary small catalog-source-tools" onClick={() => onPrepare(rawSourceById.get(selected.id) ?? selected)}>{t("catalogSourceTools")}</button>}
          </div> : <p>{t("catalogSelectSource")}</p>}
          {editorRecords.length > 0 && (
            <div className="catalog-working-summaries">
              {editorRecords.map((rec) => {
                const rawRec = rawSourceById.get(rec.id) ?? rec;
                const isCurrent = rec.id === selected?.id;
                const editorActive = Boolean(draftScope?.active && viewMode === "split" && (!compact || readerOpen) && isCurrent);
                const editorSuspended = Boolean(
                  !isCurrent ||
                    ((!compact || readerOpen) &&
                      (viewMode === "table" || (pageSuspended && draftScope?.active === false))),
                );
                return (
                  <div key={rec.id} hidden={!isCurrent}>
                    <WorkingSummaryEditor
                      record={rawRec}
                      scope={draftScope ? { ...draftScope, active: editorActive } : undefined}
                      suspended={editorSuspended}
                      onOpen={() => {
                        setSelectedId(rec.id);
                        handleSummarySessionChange(true, rec.id);
                        setReaderOpen(true);
                      }}
                      onSessionChange={handleSummarySessionChange}
                      t={t}
                      onSaved={onWorkingSummarySaved}
                    />
                  </div>
                );
              })}
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}
