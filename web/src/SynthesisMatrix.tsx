import { classifyLabelTone, GitHubLabelText } from "./BrandIcons";
import { readingScopeTone, sourceTags } from "./LiteratureLibrary";
import type { Locale, ResearchRecord } from "./types";
import { effectiveScreeningDecision } from "./VisualInsights";

const asText = (value: unknown): string =>
  typeof value === "string" || typeof value === "number" ? String(value) : "";

function buildScreeningLookup(screenings: ResearchRecord[]): Map<string, "include" | "exclude"> {
  const map = new Map<string, "include" | "exclude">();
  for (const record of screenings) {
    if (record.kind !== "screening" || typeof record.data.source_id !== "string") continue;
    const raw = record.data.decision;
    const hasValidRationale =
      record.data.rationale === undefined ||
      (typeof record.data.rationale === "string" && record.data.rationale.trim().length > 0);
    if (hasValidRationale && (raw === "include" || raw === "exclude")) {
      map.set(record.data.source_id, raw);
    } else {
      map.delete(record.data.source_id);
    }
  }
  return map;
}

function buildClaimCitationCounts(claims: ResearchRecord[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const claim of claims) {
    if (!Array.isArray(claim.data.source_ids)) continue;
    const uniqueForClaim = new Set<string>();
    for (const rawId of claim.data.source_ids) {
      const id = asText(rawId).trim();
      if (id) uniqueForClaim.add(id);
    }
    for (const id of uniqueForClaim) {
      counts.set(id, (counts.get(id) ?? 0) + 1);
    }
  }
  return counts;
}

function firstAuthorShort(value: unknown): string {
  if (typeof value === "string") return value.trim();
  if (!Array.isArray(value) || value.length === 0) return "";
  const first = value[0];
  let name = "";
  if (typeof first === "string") name = first.trim();
  else if (first && typeof first === "object") {
    const obj = first as Record<string, unknown>;
    name = asText(obj.family || obj.name).trim();
  }
  if (!name) return "";
  return value.length > 1 ? `${name} et al.` : name;
}

const MATRIX_COPY = {
  "zh-TW": {
    ariaLabel: "文獻 × 主題標籤與證據交叉矩陣",
    summaryCohort: (n: number) => `共 ${n} 篇文獻`,
    summaryCited: (cited: number, total: number) => `證據已引用 ${cited}/${total} 篇`,
    colPaper: "文獻與年份",
    colScope: "閱讀範圍",
    colScreening: "篩選",
    colCitations: "證據引用數",
    colNoTags: "主題標籤",
    scopeFull: "全文",
    scopeAbstract: "摘要",
    scopeMeta: "書目",
    screenInclude: "已納入",
    screenExclude: "已排除",
    screenPending: "待篩選",
    citationsAria: (n: number) => `被 ${n} 條證據主張引用`,
    hasTagAria: (paperTitle: string, tag: string) => `${paperTitle} 標記有 #${tag}`,
    emptyState: "目前篩選條件下無文獻可顯示交叉矩陣",
    untitled: "未命名文獻",
  },
  en: {
    ariaLabel: "Literature × Theme Labels & Evidence Synthesis Matrix",
    summaryCohort: (n: number) => `${n} papers in cohort`,
    summaryCited: (cited: number, total: number) => `Cited in Evidence: ${cited}/${total}`,
    colPaper: "Paper & Year",
    colScope: "Scope",
    colScreening: "Triage",
    colCitations: "Evidence Citations",
    colNoTags: "Theme Labels",
    scopeFull: "Full-text",
    scopeAbstract: "Abstract",
    scopeMeta: "Metadata",
    screenInclude: "Included",
    screenExclude: "Excluded",
    screenPending: "Unscreened",
    citationsAria: (n: number) => `Cited by ${n} evidence claims`,
    hasTagAria: (paperTitle: string, tag: string) => `${paperTitle} carries #${tag}`,
    emptyState: "No papers match the current filter to build the synthesis matrix",
    untitled: "Untitled source",
  },
} as const;

export interface SynthesisMatrixProps {
  sources: ResearchRecord[];
  screenings: ResearchRecord[];
  claims?: ResearchRecord[];
  locale?: Locale;
  selectedId?: string | null;
  onSelectPaper: (record: ResearchRecord) => void;
  onToggleTag?: (tag: string) => void;
  selectedTags?: string[];
}

export function SynthesisMatrix({
  sources,
  screenings,
  claims = [],
  locale = "en",
  selectedId,
  onSelectPaper,
  onToggleTag,
  selectedTags = [],
}: SynthesisMatrixProps) {
  const c = MATRIX_COPY[locale === "zh-TW" ? "zh-TW" : "en"];

  if (sources.length === 0) {
    return (
      <section className="vr-matrix-empty" aria-label={c.ariaLabel}>
        <p className="vr-empty-note">{c.emptyState}</p>
      </section>
    );
  }

  const screeningMap = buildScreeningLookup(screenings);
  const claimCounts = buildClaimCitationCounts(claims);

  const tagFreq = new Map<string, { label: string; count: number }>();
  const rowTagSets = new Map<string, Set<string>>();

  for (const record of sources) {
    const tags = sourceTags(record);
    const lowerSet = new Set<string>();
    for (const tag of tags) {
      const key = tag.toLocaleLowerCase();
      lowerSet.add(key);
      const existing = tagFreq.get(key);
      if (existing) existing.count++;
      else tagFreq.set(key, { label: tag, count: 1 });
    }
    rowTagSets.set(record.id, lowerSet);
  }

  const topTags = [...tagFreq.values()]
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
    .slice(0, 6);

  const selectedTagSet = new Set(selectedTags.map((t) => t.toLocaleLowerCase()));
  const citedPaperCount = sources.filter((s) => (claimCounts.get(s.id) ?? 0) > 0).length;

  return (
    <section className="vr-matrix-section" aria-label={c.ariaLabel}>
      <div className="vr-matrix-bar">
        <span className="vr-matrix-kpi">{c.summaryCohort(sources.length)}</span>
        <span className="vr-matrix-kpi is-accent">
          {c.summaryCited(citedPaperCount, sources.length)}
        </span>
      </div>

      <div className="vr-matrix-wrap">
        <table className="vr-matrix-table">
          <thead>
            <tr>
              <th scope="col" className="vr-matrix-col-paper">
                {c.colPaper}
              </th>
              <th scope="col" className="vr-matrix-col-center">
                {c.colScope}
              </th>
              <th scope="col" className="vr-matrix-col-center">
                {c.colScreening}
              </th>
              <th scope="col" className="vr-matrix-col-center">
                {c.colCitations}
              </th>
              {topTags.length > 0 ? (
                topTags.map((tag) => {
                  const tone = classifyLabelTone(tag.label);
                  const isPressed = selectedTagSet.has(tag.label.toLocaleLowerCase());
                  return (
                    <th key={tag.label} scope="col" className="vr-matrix-col-tag">
                      {onToggleTag ? (
                        <button
                          type="button"
                          className={`tag-chip tag-chip-btn label-tone-${tone}`}
                          aria-pressed={isPressed}
                          onClick={() => onToggleTag(tag.label)}
                        >
                          <GitHubLabelText label={tag.label} />
                          <span className="pill-count">{tag.count}</span>
                        </button>
                      ) : (
                        <span className={`tag-chip label-tone-${tone}`}>
                          <GitHubLabelText label={tag.label} />
                          <span className="pill-count">{tag.count}</span>
                        </span>
                      )}
                    </th>
                  );
                })
              ) : (
                <th scope="col" className="vr-matrix-col-center">
                  {c.colNoTags}
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {sources.map((record) => {
              const title = asText(record.data.title).trim() || c.untitled;
              const year = asText(record.data.year).trim();
              const author = firstAuthorShort(record.data.authors);
              const tone = readingScopeTone(record);
              const decision = effectiveScreeningDecision(record, screeningMap);
              const citeCount = claimCounts.get(record.id) ?? 0;
              const paperTags = rowTagSets.get(record.id) ?? new Set<string>();
              const isSelected = selectedId === record.id;

              const scopeText =
                tone === "full"
                  ? c.scopeFull
                  : tone === "abstract"
                    ? c.scopeAbstract
                    : c.scopeMeta;
              const scopeGlyph = tone === "full" || tone === "abstract" ? "●" : "○";

              return (
                <tr key={record.id} className={isSelected ? "is-selected" : undefined}>
                  <td className="vr-matrix-paper-cell">
                    <button
                      type="button"
                      className="vr-matrix-paper-btn"
                      onClick={() => onSelectPaper(record)}
                    >
                      <span className="vr-matrix-paper-title">{title}</span>
                      <span className="vr-matrix-paper-meta">
                        {year && <span className="vr-matrix-year">{year}</span>}
                        {author && <span>{author}</span>}
                      </span>
                    </button>
                  </td>

                  <td className="vr-matrix-cell-center">
                    <span className={`vr-matrix-scope is-${tone}`}>
                      <span aria-hidden="true">{scopeGlyph}</span> {scopeText}
                    </span>
                  </td>

                  <td className="vr-matrix-cell-center">
                    {decision === "include" ? (
                      <span
                        className="vr-matrix-screen is-include"
                        role="img"
                        aria-label={c.screenInclude}
                        title={c.screenInclude}
                      >
                        ✓
                      </span>
                    ) : decision === "exclude" ? (
                      <span
                        className="vr-matrix-screen is-exclude"
                        role="img"
                        aria-label={c.screenExclude}
                        title={c.screenExclude}
                      >
                        ✕
                      </span>
                    ) : (
                      <span
                        className="vr-matrix-screen is-pending"
                        role="img"
                        aria-label={c.screenPending}
                        title={c.screenPending}
                      >
                        ·
                      </span>
                    )}
                  </td>

                  <td className="vr-matrix-cell-center">
                    <span
                      className={`vr-cite-count-badge${
                        citeCount > 0
                          ? " is-cited"
                          : decision === "include"
                            ? " is-uncited-included"
                            : " is-zero"
                      }`}
                      aria-label={c.citationsAria(citeCount)}
                    >
                      {citeCount}
                    </span>
                  </td>

                  {topTags.length > 0 ? (
                    topTags.map((tag) => {
                      const hasTag = paperTags.has(tag.label.toLocaleLowerCase());
                      const tagTone = classifyLabelTone(tag.label);
                      return (
                        <td key={tag.label} className="vr-matrix-cell-center vr-matrix-dot-cell">
                          {hasTag ? (
                            <span
                              className={`vr-matrix-dot label-tone-${tagTone}`}
                              role="img"
                              aria-label={c.hasTagAria(title, tag.label)}
                            >
                              ●
                            </span>
                          ) : (
                            <span className="vr-matrix-empty" aria-hidden="true">
                              ·
                            </span>
                          )}
                        </td>
                      );
                    })
                  ) : (
                    <td className="vr-matrix-cell-center">
                      <span className="vr-matrix-empty" aria-hidden="true">
                        —
                      </span>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
