import { useState } from "react";
import { MutationForm, ReadText, SourceLink } from "./components";
import { statusLabel, type Translate } from "./i18n";
import type { ResearchRecord } from "./types";

const text = (value: unknown) => typeof value === "string" || typeof value === "number" ? String(value) : "";
const category = (record: ResearchRecord) => text(record.data.category) || text(record.data.sub_category);
const strings = (value: unknown) => Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];

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

export function LiteratureLibrary({ sources, screenings, t, onScreen, onPrepare, matches }: {
  sources: ResearchRecord[];
  screenings: ResearchRecord[];
  t: Translate;
  onScreen: (sourceId: string, decision: string, rationale: string) => Promise<void>;
  onPrepare: (record: ResearchRecord) => void;
  matches?: Map<string, ResearchRecord[]>;
}) {
  const [query, setQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const categories = [...new Set(sources.map(category).filter(Boolean))].sort();
  const search = query.trim().toLocaleLowerCase();
  const visible = sources.filter((record) =>
    (!selectedCategory || category(record) === selectedCategory) &&
    (!search || [record.data.title, record.data.year, record.data.relevance, category(record), ...strings(record.data.tags), ...strings(record.data.labels)]
      .map(text).join(" ").toLocaleLowerCase().includes(search)),
  );
  const selected = visible.find((record) => record.id === selectedId) ?? visible[0];
  const latest = selected ? [...screenings].reverse().find((record) => record.data.source_id === selected.id) : undefined;
  const summary = selected && (text(selected.data.summary) || text(selected.data.abstract));
  const note = selected?.kind === "library-note";

  return (
    <section className="literature-library" aria-label={t("catalogTitle")}>
      <div className="catalog-heading">
        <div><h2>{t("catalogTitle")}</h2><p>{t("catalogIntro")}</p></div>
        <span className="catalog-total">{sources.length} {t("catalogItems")}</span>
      </div>
      <div className="catalog-toolbar">
        <label className="catalog-search">{t("catalogSearch")}
          <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("catalogSearchHint")} />
        </label>
        <label>{t("catalogCategory")}
          <select value={selectedCategory} onChange={(event) => setSelectedCategory(event.target.value)}>
            <option value="">{t("catalogAllCategories")}</option>
            {categories.map((value) => <option key={value} value={value}>{categoryName(value, t)} ({sources.filter((record) => category(record) === value).length})</option>)}
          </select>
        </label>
        <p className="catalog-match" role="status">{visible.length} / {sources.length} {t("catalogItems")}</p>
      </div>
      <div className="catalog-workspace">
        <div className="catalog-list">
          {visible.length ? (
            <table>
              <thead><tr><th scope="col">{t("title")}</th><th scope="col">{t("catalogYear")}</th><th scope="col">{t("catalogCategory")}</th><th scope="col">{t("catalogCoverage")}</th></tr></thead>
              <tbody>{visible.map((record) => (
                <tr key={record.id} className={selected?.id === record.id ? "is-selected" : undefined}>
                  <td><button className="catalog-title" aria-pressed={selected?.id === record.id} onClick={() => setSelectedId(record.id)}>{text(record.data.title)}</button><span className="catalog-origin">{record.kind === "library-note" ? t("libraryNoteOrigin") : t("libraryWorkspaceOrigin")}{Boolean(matches?.get(record.id)?.length) && <> · {t("libraryIdentityMatch")}</>}</span></td>
                  <td>{text(record.data.year) || "—"}</td>
                  <td><span className="catalog-category">{categoryName(category(record), t)}</span></td>
                  <td>{readingScope(record, t)}</td>
                </tr>
              ))}</tbody>
            </table>
          ) : <p className="catalog-empty">{sources.length ? t("catalogNoMatches") : t("noSources")}</p>}
        </div>
        <aside className="catalog-detail" aria-label={t("catalogDetail")}>
          {selected ? <>
            <p className="catalog-detail-label">{t("catalogDetail")}</p>
            <h3>{text(selected.data.title)}</h3>
            <div className="catalog-meta"><span>{text(selected.data.year) || "—"}</span><span>{categoryName(category(selected), t)}</span><span>{statusLabel(text(selected.data.identity_status) || "unverified", t)}</span></div>
            {note && <p className="catalog-missing">{t("libraryReadOnly")}</p>}
            <section><h4>{t("catalogCoverage")}</h4><p>{readingScope(selected, t)}</p><p className="small muted">{text(selected.data.reading_level_note) || t("catalogScopeHelp")}</p></section>
            <section><h4>{note ? t("librarySavedAbstract") : t("catalogSavedSummary")}</h4>{summary ? <ReadText value={summary} /> : <p className="catalog-missing">{t("catalogNoSummary")}</p>}</section>
            <section><h4>{t("catalogRelevance")}</h4>{text(selected.data.relevance) ? <ReadText value={text(selected.data.relevance)} /> : <p className="muted">{t("catalogNoRelevance")}</p>}</section>
            <section><h4>{t("catalogSource")}</h4>
              {selected.data.locator_kind === "local-copy" ? <p>{t("intakeLocalLocator")}</p> : <SourceLink locator={selected.data.locator} title={t("catalogOriginalSource")} />}
              {text(selected.data.doi) && <p className="small">DOI: {text(selected.data.doi)}</p>}
              {note && <><p className="small">{t("libraryNotePath")}: <code>{text(selected.data.note_path)}</code></p><p className="small">{t("libraryMetadataStatus")}: {selected.data.metadata_status === "available" ? t("libraryAvailable") : t("libraryUnavailableMetadata")}</p>{text(selected.data.saved_reading_status) && <p className="small">{t("librarySavedStatus")}: {text(selected.data.saved_reading_status)}</p>}</>}
              {Boolean(matches?.get(selected.id)?.length) && <div className="catalog-missing"><strong>{t("libraryIdentityMatch")}</strong><p>{t("libraryMatchHelp")}</p><ul>{matches!.get(selected.id)!.map((other) => <li key={other.id}>{text(other.data.title)} · {other.kind === "library-note" ? t("libraryNoteOrigin") : t("libraryWorkspaceOrigin")}<br /><code>{other.kind === "library-note" ? text(other.data.note_path) : other.id}</code></li>)}</ul></div>}
              {text(selected.data.publication_version) && <p className="small">{text(selected.data.publication_version)}</p>}
              <details className="catalog-provenance"><summary>{t("catalogProvenance")}</summary><p>{note ? t("libraryNoteOrigin") : text(selected.data.batch_id) || t("catalogUnknownOrigin")}</p>{note && <p className="small">{t("libraryMetadataHash")}: <code>{text(selected.data.frontmatter_sha256) || t("libraryUnavailableMetadata")}</code></p>}{Array.isArray(selected.data.prior_batch_matches) && selected.data.prior_batch_matches.length > 0 && <p>{t("catalogPriorMatch")}</p>}</details>
            </section>
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
