import { useState } from "react";
import { readingScopeTone, type ScopeTone } from "./LiteratureLibrary";
import type { DeliveryAction, Locale, Page, ResearchRecord, Task } from "./types";
import { workingSummary } from "./WorkingSummaryEditor";

export type StageLedState = "ok" | "active" | "idle";
export type RiskSeverity = "ok" | "warn" | "danger";

const asText = (value: unknown): string =>
  typeof value === "string" || typeof value === "number" ? String(value) : "";

function resolveScreeningMap(screenings: ResearchRecord[]): Map<string, "include" | "exclude"> {
  const map = new Map<string, "include" | "exclude">();
  for (const record of screenings) {
    if (record.kind !== "screening" || typeof record.data.source_id !== "string") continue;
    const rawDecision = record.data.decision;
    const hasValidRationale =
      record.data.rationale === undefined ||
      (typeof record.data.rationale === "string" && record.data.rationale.trim().length > 0);
    if (hasValidRationale && (rawDecision === "include" || rawDecision === "exclude")) {
      map.set(record.data.source_id, rawDecision);
    } else {
      map.delete(record.data.source_id);
    }
  }
  return map;
}

export function effectiveScreeningDecision(
  source: ResearchRecord,
  screeningMap: Map<string, "include" | "exclude">,
): "include" | "exclude" | null {
  const mapped = screeningMap.get(source.id);
  if (mapped) return mapped;
  const inline = source.data.screening;
  if (inline === "include" || inline === "exclude") return inline;
  return null;
}

export function hasSavedSummaryOrAbstract(source: ResearchRecord): boolean {
  const summary = source.data.summary;
  if (typeof summary === "string" && summary.trim().length > 0) return true;
  const abstract = source.data.abstract;
  if (typeof abstract === "string" && abstract.trim().length > 0) return true;
  if (workingSummary(source)) return true;
  if (
    source.kind === "source" &&
    "native_summary_available" in source &&
    (source as unknown as Record<string, unknown>).native_summary_available === true
  ) {
    return true;
  }
  return false;
}

export function hasSavedDoi(source: ResearchRecord): boolean {
  return typeof source.data.doi === "string" && source.data.doi.trim().length > 0;
}

function claimSourceIdList(claim: ResearchRecord): string[] {
  if (!Array.isArray(claim.data.source_ids)) return [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of claim.data.source_ids) {
    const id = asText(raw).trim();
    if (id && !seen.has(id)) {
      seen.add(id);
      out.push(id);
    }
  }
  return out;
}

export interface ResearchBlindSpots {
  abstractOnlyClaims: ResearchRecord[];
  singleSourceClaims: ResearchRecord[];
  uncitedIncludedSources: ResearchRecord[];
  metadataGapSources: ResearchRecord[];
  totalClaims: number;
  includedSourceCount: number;
  robustnessScore: number;
}

/**
 * Pure zero-fetch computation of high-leverage research synthesis blind spots:
 * 1. Abstract-only grounding risk (claims with >= 1 source where 0 sources are full-text)
 * 2. Single-source fragility (claims backed by exactly 1 source)
 * 3. Uncited included cohort (sources screened as include but cited by 0 claims)
 * 4. Metadata / DOI gaps (included sources missing summary/abstract or missing DOI)
 */
export function computeResearchBlindSpots(
  sources: ResearchRecord[],
  screenings: ResearchRecord[],
  claims: ResearchRecord[],
): ResearchBlindSpots {
  const activeSources = sources.filter((s) => s.data.archived !== true);
  const sourceById = new Map(sources.map((s) => [s.id, s]));
  const screeningMap = resolveScreeningMap(screenings);

  const includedSources = activeSources.filter(
    (s) => effectiveScreeningDecision(s, screeningMap) === "include",
  );

  const abstractOnlyClaims: ResearchRecord[] = [];
  const singleSourceClaims: ResearchRecord[] = [];
  const citedSourceIds = new Set<string>();

  for (const claim of claims) {
    const ids = claimSourceIdList(claim);
    for (const id of ids) {
      citedSourceIds.add(id);
    }
    if (ids.length === 1) {
      singleSourceClaims.push(claim);
    }
    if (ids.length >= 1) {
      const hasFullText = ids.some((id) => {
        const linked = sourceById.get(id);
        return Boolean(linked && readingScopeTone(linked) === "full");
      });
      if (!hasFullText) {
        abstractOnlyClaims.push(claim);
      }
    }
  }

  const uncitedIncludedSources = includedSources.filter((s) => !citedSourceIds.has(s.id));
  const metadataGapSources = includedSources.filter(
    (s) => !hasSavedSummaryOrAbstract(s) || !hasSavedDoi(s),
  );

  let robustnessScore = 0;
  if (activeSources.length > 0 || claims.length > 0) {
    const rAbstract = claims.length > 0 ? abstractOnlyClaims.length / claims.length : 0;
    const rSingle = claims.length > 0 ? singleSourceClaims.length / claims.length : 0;
    const rUncited =
      includedSources.length > 0 ? uncitedIncludedSources.length / includedSources.length : 0;
    const rMeta =
      includedSources.length > 0 ? metadataGapSources.length / includedSources.length : 0;

    if (claims.length === 0) {
      const litPenalty = rUncited * 25 + rMeta * 25;
      robustnessScore = Math.max(0, Math.min(100, Math.round(60 - litPenalty)));
    } else {
      const penalty = rAbstract * 35 + rSingle * 20 + rUncited * 25 + rMeta * 20;
      robustnessScore = Math.max(0, Math.min(100, Math.round(100 - penalty)));
    }
  }

  return {
    abstractOnlyClaims,
    singleSourceClaims,
    uncitedIncludedSources,
    metadataGapSources,
    totalClaims: claims.length,
    includedSourceCount: includedSources.length,
    robustnessScore,
  };
}

const COPY = {
  "zh-TW": {
    stepperAria: "研究工作流階段進度",
    stage1: "1. 文獻蒐集",
    stage1Sub: "Literature",
    stage2: "2. 篩選納入",
    stage2Sub: "Screening",
    stage3: "3. 證據主張",
    stage3Sub: "Evidence",
    stage4: "4. 文稿交付",
    stage4Sub: "Manuscript",
    papersUnit: (n: number) => `${n} 篇`,
    fullTextSub: (n: number) => `全文 ${n}`,
    includedRatio: (inc: number, total: number) => `納入 ${inc}/${total}`,
    claimsRatio: (grounded: number, total: number) => `${grounded}/${total} 條`,
    manuscriptReady: "已就緒",
    manuscriptSections: (n: number) => `${n} 節大綱`,
    manuscriptPending: "待起草",
    chartsAria: "文獻年份與覆蓋率視覺分析",
    yearChartTitle: "出版年份分佈",
    yearChartHint: "點擊年份柱可篩選文獻庫",
    legendFull: "全文",
    legendPartial: "僅摘要/書目",
    undatedBadge: (n: number) => `未標年份 ${n}`,
    noYearData: "尚無年份資料",
    yearBarAria: (year: string, total: number, full: number) =>
      `${year} 年：共 ${total} 篇（全文 ${full} 篇），點擊篩選`,
    donutTitle: "閱讀範圍與篩選覆蓋",
    donutCenterLabel: "已納入",
    scopeFull: "全文",
    scopeAbstract: "僅摘要",
    scopeMeta: "僅書目",
    triageIncluded: "納入",
    triagePending: "待審",
    triageExcluded: "排除",
    noSourcesYet: "尚無文獻可繪製視覺圖表",
    radarTitle: "證據風險與研究盲點雷達",
    radarSub: "即時交叉比對閱讀深度、單一來源依賴與未引用核心文獻",
    robustnessLabel: "證據穩健度",
    statusHealthy: "0 項",
    statusCaution: (n: number) => `${n} 項需留意`,
    statusHighRisk: (n: number) => `${n} 項高風險`,
    qAbstractTitle: "僅摘要支撐主張",
    qAbstractDesc: "主張連結之文獻皆非全文，引用具體數據風險較高",
    qSingleTitle: "單一文獻脆弱主張",
    qSingleDesc: "僅仰賴 1 篇文獻支撐，建議補充交叉證據",
    qUncitedTitle: "已納入卻未引用文獻",
    qUncitedDesc: "已篩選納入但尚未連結至任何證據主張的孤兒文獻",
    qMetaTitle: "核心文獻缺摘要或 DOI",
    qMetaDesc: "已納入文獻缺少摘要或 DOI，影響引用與驗證完整性",
    jumpEvidence: "檢視證據",
    jumpLiterature: "開啟文獻",
    allClearItem: "目前無此類風險項目",
  },
  en: {
    stepperAria: "Research workflow stage progress",
    stage1: "1. Literature",
    stage1Sub: "Collection",
    stage2: "2. Screening",
    stage2Sub: "Inclusion",
    stage3: "3. Evidence",
    stage3Sub: "Grounding",
    stage4: "4. Manuscript",
    stage4Sub: "Delivery",
    papersUnit: (n: number) => `${n} papers`,
    fullTextSub: (n: number) => `${n} full-text`,
    includedRatio: (inc: number, total: number) => `${inc}/${total} in`,
    claimsRatio: (grounded: number, total: number) => `${grounded}/${total} claims`,
    manuscriptReady: "Ready",
    manuscriptSections: (n: number) => `${n} sections`,
    manuscriptPending: "Pending",
    chartsAria: "Literature publication year and coverage analytics",
    yearChartTitle: "Publication Year Distribution",
    yearChartHint: "Click any year bar to filter Literature",
    legendFull: "Full-text",
    legendPartial: "Abstract / Meta",
    undatedBadge: (n: number) => `${n} undated`,
    noYearData: "No publication years recorded yet",
    yearBarAria: (year: string, total: number, full: number) =>
      `Year ${year}: ${total} papers (${full} full-text). Click to filter`,
    donutTitle: "Coverage & Screening Triage",
    donutCenterLabel: "Included",
    scopeFull: "Full-text",
    scopeAbstract: "Abstract",
    scopeMeta: "Metadata",
    triageIncluded: "Included",
    triagePending: "Awaiting",
    triageExcluded: "Excluded",
    noSourcesYet: "Add sources to visualize year distribution and scope coverage",
    radarTitle: "Evidence Risk & Blind-Spot Radar",
    radarSub: "Cross-checks reading depth, single-source fragility, and uncited included papers",
    robustnessLabel: "Evidence Robustness",
    statusHealthy: "0 items",
    statusCaution: (n: number) => `${n} caution`,
    statusHighRisk: (n: number) => `${n} high risk`,
    qAbstractTitle: "Abstract-Only Grounded Claims",
    qAbstractDesc: "Claims backed by >= 1 source where 0 sources are full-text",
    qSingleTitle: "Single-Source Fragility",
    qSingleDesc: "Claims relying on a single source without triangulation",
    qUncitedTitle: "Uncited Included Cohort",
    qUncitedDesc: "Included papers referenced by 0 Evidence claims",
    qMetaTitle: "Core Metadata / DOI Gaps",
    qMetaDesc: "Included papers missing a saved summary/abstract or DOI",
    jumpEvidence: "Inspect Evidence",
    jumpLiterature: "Open Literature",
    allClearItem: "No blind spots detected in this quadrant",
  },
} as const;

export interface ResearchStageStepperProps {
  sources: ResearchRecord[];
  screenings: ResearchRecord[];
  claims: ResearchRecord[];
  outlines?: ResearchRecord[];
  manuscript?: Record<string, unknown> | null;
  actions?: DeliveryAction[];
  tasks?: Task[];
  currentPage?: Page;
  locale?: Locale;
  onNavigate: (page: Page) => void;
}

export function ResearchStageStepper({
  sources,
  screenings,
  claims,
  outlines = [],
  manuscript = null,
  actions = [],
  tasks = [],
  currentPage,
  locale = "en",
  onNavigate,
}: ResearchStageStepperProps) {
  const c = COPY[locale === "zh-TW" ? "zh-TW" : "en"];
  const activeSources = sources.filter((s) => s.data.archived !== true);
  const screeningMap = resolveScreeningMap(screenings);

  const totalSources = activeSources.length;
  const fullTextCount = activeSources.filter((s) => readingScopeTone(s) === "full").length;
  const readySources = activeSources.filter(
    (s) => readingScopeTone(s) === "full" || hasSavedSummaryOrAbstract(s),
  ).length;

  const screenableSources = activeSources.filter((s) => s.kind === "source");
  const screenableTotal = screenableSources.length || totalSources;
  let includedCount = 0;
  let excludedCount = 0;
  for (const src of screenableSources.length ? screenableSources : activeSources) {
    const dec = effectiveScreeningDecision(src, screeningMap);
    if (dec === "include") includedCount++;
    else if (dec === "exclude") excludedCount++;
  }
  const decidedCount = includedCount + excludedCount;

  const totalClaims = claims.length;
  const groundedClaims = claims.filter((cl) => claimSourceIdList(cl).length > 0).length;

  const hasManuscript = Boolean(manuscript && Object.keys(manuscript).length > 0);
  const completedDeliveries = actions.filter(
    (a) => a.status === "completed" || a.status === "approved",
  ).length;
  const draftTasks = tasks.filter((tk) =>
    ["outline", "draft", "revise"].includes(tk.operation),
  ).length;

  const stage1Led: StageLedState =
    totalSources === 0 ? "active" : readySources > 0 || decidedCount > 0 ? "ok" : "active";
  const stage1Progress =
    totalSources === 0
      ? 0
      : Math.max(18, Math.min(100, Math.round((readySources / totalSources) * 100)));

  const stage2Led: StageLedState =
    screenableTotal === 0
      ? "idle"
      : includedCount > 0 && decidedCount === screenableTotal
        ? "ok"
        : decidedCount > 0 || totalSources > 0
          ? "active"
          : "idle";
  const stage2Progress =
    screenableTotal === 0 ? 0 : Math.min(100, Math.round((decidedCount / screenableTotal) * 100));

  const stage3Led: StageLedState =
    totalClaims > 0 && groundedClaims === totalClaims
      ? "ok"
      : totalClaims > 0 || includedCount > 0
        ? "active"
        : "idle";
  const stage3Progress =
    totalClaims === 0 ? 0 : Math.min(100, Math.round((groundedClaims / totalClaims) * 100));

  const stage4Led: StageLedState =
    hasManuscript || completedDeliveries > 0
      ? "ok"
      : outlines.length > 0 || draftTasks > 0 || groundedClaims > 0
        ? "active"
        : "idle";
  const stage4Progress =
    hasManuscript || completedDeliveries > 0
      ? 100
      : outlines.length > 0
        ? 65
        : draftTasks > 0
          ? 35
          : 0;

  const stages: {
    key: string;
    page: Page;
    title: string;
    sub: string;
    pill: string;
    detail: string;
    led: StageLedState;
    progress: number;
  }[] = [
    {
      key: "literature",
      page: "literature",
      title: c.stage1,
      sub: c.stage1Sub,
      pill: c.papersUnit(totalSources),
      detail: c.fullTextSub(fullTextCount),
      led: stage1Led,
      progress: stage1Progress,
    },
    {
      key: "screening",
      page: "literature",
      title: c.stage2,
      sub: c.stage2Sub,
      pill: c.includedRatio(includedCount, screenableTotal),
      detail: `${stage2Progress}%`,
      led: stage2Led,
      progress: stage2Progress,
    },
    {
      key: "evidence",
      page: "evidence",
      title: c.stage3,
      sub: c.stage3Sub,
      pill: c.claimsRatio(groundedClaims, totalClaims),
      detail: `${stage3Progress}%`,
      led: stage3Led,
      progress: stage3Progress,
    },
    {
      key: "manuscript",
      page: "manuscript",
      title: c.stage4,
      sub: c.stage4Sub,
      pill:
        hasManuscript || completedDeliveries > 0
          ? c.manuscriptReady
          : outlines.length > 0
            ? c.manuscriptSections(outlines.length)
            : c.manuscriptPending,
      detail: `${stage4Progress}%`,
      led: stage4Led,
      progress: stage4Progress,
    },
  ];

  return (
    <section className="vr-stage-stepper" role="group" aria-label={c.stepperAria}>
      {stages.map((stage, idx) => {
        const isCurrent = currentPage === stage.page && idx !== 1;
        return (
          <button
            key={stage.key}
            type="button"
            className={`vr-stage-step is-${stage.led}${isCurrent ? " is-current" : ""}`}
            onClick={() => onNavigate(stage.page)}
          >
            <div className="vr-stage-top">
              <span className="vr-stage-title-wrap">
                <span className={`vr-led is-${stage.led}`} aria-hidden="true" />
                <span className="vr-stage-title">{stage.title}</span>
              </span>
              <span className="vr-stage-pill">{stage.pill}</span>
            </div>
            <div className="vr-stage-bar" aria-hidden="true">
              <span
                className={`vr-stage-bar-fill is-${stage.led}`}
                style={{ width: `${stage.progress}%` }}
              />
            </div>
            <div className="vr-stage-meta">
              <span>{stage.sub}</span>
              <span className="vr-stage-pct">{stage.detail}</span>
            </div>
          </button>
        );
      })}
    </section>
  );
}

export interface LiteratureVisualChartsProps {
  sources: ResearchRecord[];
  screenings: ResearchRecord[];
  locale?: Locale;
  selectedYear?: string;
  onSelectYear?: (year: string) => void;
  onSelectScope?: (scope: ScopeTone) => void;
  onNavigateLiterature?: () => void;
}

interface YearBucket {
  year: string;
  total: number;
  full: number;
  partial: number;
}

export function LiteratureVisualCharts({
  sources,
  screenings,
  locale = "en",
  selectedYear,
  onSelectYear,
  onSelectScope,
  onNavigateLiterature,
}: LiteratureVisualChartsProps) {
  const c = COPY[locale === "zh-TW" ? "zh-TW" : "en"];
  const [activeScopeSlice, setActiveScopeSlice] = useState<"full" | "abstract" | "metadata" | null>(
    null,
  );
  const activeSources = sources.filter((s) => s.data.archived !== true);
  const screeningMap = resolveScreeningMap(screenings);

  if (activeSources.length === 0) {
    return (
      <section className="vr-charts-empty" aria-label={c.chartsAria}>
        <p className="vr-empty-note">{c.noSourcesYet}</p>
      </section>
    );
  }

  const byYear = new Map<string, YearBucket>();
  let undatedCount = 0;
  let fullCount = 0;
  let abstractCount = 0;
  let metaCount = 0;
  let includedCount = 0;
  let excludedCount = 0;
  let awaitingCount = 0;

  for (const src of activeSources) {
    const tone = readingScopeTone(src);
    if (tone === "full") fullCount++;
    else if (tone === "abstract") abstractCount++;
    else metaCount++;

    const dec = effectiveScreeningDecision(src, screeningMap);
    if (dec === "include") includedCount++;
    else if (dec === "exclude") excludedCount++;
    else awaitingCount++;

    const yr = asText(src.data.year).trim();
    if (/^\d{4}$/.test(yr)) {
      let bucket = byYear.get(yr);
      if (!bucket) {
        bucket = { year: yr, total: 0, full: 0, partial: 0 };
        byYear.set(yr, bucket);
      }
      bucket.total++;
      if (tone === "full") bucket.full++;
      else bucket.partial++;
    } else {
      undatedCount++;
    }
  }

  const sortedYears = [...byYear.values()]
    .sort((a, b) => Number(a.year) - Number(b.year))
    .slice(-10);
  const maxYearCount = Math.max(1, ...sortedYears.map((b) => b.total));

  const total = activeSources.length;
  const radius = 44;
  const circumference = 2 * Math.PI * radius;

  const segments: {
    key: "full" | "abstract" | "metadata";
    label: string;
    count: number;
    strokeVar: string;
  }[] = [
    { key: "full", label: c.scopeFull, count: fullCount, strokeVar: "var(--scope-full-dot)" },
    {
      key: "abstract",
      label: c.scopeAbstract,
      count: abstractCount,
      strokeVar: "var(--scope-abstract-dot)",
    },
    { key: "metadata", label: c.scopeMeta, count: metaCount, strokeVar: "var(--scope-meta-dot)" },
  ];

  let cumulativeLength = 0;
  const arcs = segments.map((seg) => {
    const segLength = total > 0 ? (seg.count / total) * circumference : 0;
    const offset = cumulativeLength;
    cumulativeLength += segLength;
    return { ...seg, segLength, offset };
  });

  return (
    <section className="vr-charts-grid" aria-label={c.chartsAria}>
      <article className="vr-chart-card">
        <header className="vr-chart-header">
          <div>
            <h3 className="vr-chart-title">{c.yearChartTitle}</h3>
            <p className="vr-chart-sub">{c.yearChartHint}</p>
          </div>
          <div className="vr-chart-legend-inline">
            <span className="vr-inline-key">
              <span className="vr-key-dot is-full" aria-hidden="true" />
              {c.legendFull}
            </span>
            <span className="vr-inline-key">
              <span className="vr-key-dot is-partial" aria-hidden="true" />
              {c.legendPartial}
            </span>
            {undatedCount > 0 && (
              <span className="vr-undated-chip">{c.undatedBadge(undatedCount)}</span>
            )}
          </div>
        </header>

        {sortedYears.length > 0 ? (
          <div className="vr-histogram" role="group" aria-label={c.yearChartTitle}>
            {sortedYears.map((bucket) => {
              const fullPct = Math.round((bucket.full / maxYearCount) * 100);
              const partialPct = Math.round((bucket.partial / maxYearCount) * 100);
              const isSelected = selectedYear === bucket.year;
              return (
                <button
                  key={bucket.year}
                  type="button"
                  className={`vr-year-col${isSelected ? " is-selected" : ""}`}
                  aria-pressed={isSelected}
                  aria-label={c.yearBarAria(bucket.year, bucket.total, bucket.full)}
                  onClick={() => onSelectYear?.(bucket.year)}
                >
                  <span className="vr-year-count">{bucket.total}</span>
                  <span className="vr-year-bar-track" aria-hidden="true">
                    {bucket.full > 0 && (
                      <span
                        className="vr-year-seg is-full"
                        style={{ height: `${Math.max(8, fullPct)}%` }}
                      />
                    )}
                    {bucket.partial > 0 && (
                      <span
                        className="vr-year-seg is-partial"
                        style={{ height: `${Math.max(8, partialPct)}%` }}
                      />
                    )}
                  </span>
                  <span className="vr-year-label">{bucket.year}</span>
                </button>
              );
            })}
          </div>
        ) : (
          <p className="vr-empty-note">{c.noYearData}</p>
        )}
      </article>

      <article className="vr-chart-card">
        <header className="vr-chart-header">
          <div>
            <h3 className="vr-chart-title">{c.donutTitle}</h3>
          </div>
          <div className="vr-triage-pills">
            <span className="vr-triage-pill is-ok">
              ✓ {c.triageIncluded} {includedCount}
            </span>
            <span className="vr-triage-pill is-idle">
              · {c.triagePending} {awaitingCount}
            </span>
            {excludedCount > 0 && (
              <span className="vr-triage-pill is-muted">
                ✕ {c.triageExcluded} {excludedCount}
              </span>
            )}
          </div>
        </header>

        <div className="vr-donut-layout">
          <div className="vr-donut-wrap">
            <svg
              className="vr-donut-svg"
              viewBox="0 0 120 120"
              role="img"
              aria-label={`${c.donutTitle}: ${c.donutCenterLabel} ${includedCount}/${total}`}
            >
              <circle
                cx="60"
                cy="60"
                r={radius}
                fill="none"
                stroke="var(--wash)"
                strokeWidth="13"
              />
              {arcs.map((arc) =>
                arc.segLength > 0 ? (
                  <circle
                    key={arc.key}
                    cx="60"
                    cy="60"
                    r={radius}
                    fill="none"
                    stroke={arc.strokeVar}
                    strokeWidth={activeScopeSlice === arc.key ? "15.5" : "13"}
                    strokeDasharray={`${arc.segLength} ${Math.max(0, circumference - arc.segLength)}`}
                    strokeDashoffset={-arc.offset}
                    transform="rotate(-90 60 60)"
                    className="vr-donut-arc"
                  />
                ) : null,
              )}
            </svg>
            <div className="vr-donut-center" aria-hidden="true">
              <span className="vr-donut-center-sub">{c.donutCenterLabel}</span>
              <strong className="vr-donut-center-kpi">
                {includedCount}/{total}
              </strong>
            </div>
          </div>

          <div className="vr-donut-legend" role="group" aria-label={c.donutTitle}>
            {arcs.map((arc) => {
              const pct = total > 0 ? Math.round((arc.count / total) * 100) : 0;
              const isHighlighted = activeScopeSlice === arc.key;
              return (
                <button
                  key={arc.key}
                  type="button"
                  className={`vr-donut-legend-btn scope-${arc.key}${isHighlighted ? " is-active" : ""}`}
                  aria-pressed={isHighlighted}
                  onMouseEnter={() => setActiveScopeSlice(arc.key)}
                  onMouseLeave={() => setActiveScopeSlice(null)}
                  onClick={() => {
                    setActiveScopeSlice((prev) => (prev === arc.key ? null : arc.key));
                    if (onSelectScope) onSelectScope(arc.key);
                    else onNavigateLiterature?.();
                  }}
                >
                  <span className={`vr-scope-dot is-${arc.key}`} aria-hidden="true" />
                  <span className="vr-donut-legend-name">{arc.label}</span>
                  <span className="vr-donut-legend-nums">
                    <strong>{arc.count}</strong>
                    <span>({pct}%)</span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </article>
    </section>
  );
}

export interface EvidenceBlindSpotRadarProps {
  sources: ResearchRecord[];
  screenings: ResearchRecord[];
  claims: ResearchRecord[];
  locale?: Locale;
  compact?: boolean;
  onNavigate?: (page: Page, focusId?: string) => void;
  onOpenPaper?: (source: ResearchRecord) => void;
}

function classifyQuadrantSeverity(count: number, highRiskOnAny = false): RiskSeverity {
  if (count === 0) return "ok";
  if (highRiskOnAny || count >= 3) return "danger";
  return "warn";
}

function previewText(record: ResearchRecord): string {
  const raw = asText(record.data.title || record.data.text || record.id).trim();
  return raw.length > 52 ? `${raw.slice(0, 50)}…` : raw;
}

export function EvidenceBlindSpotRadar({
  sources,
  screenings,
  claims,
  locale = "en",
  compact = false,
  onNavigate,
  onOpenPaper,
}: EvidenceBlindSpotRadarProps) {
  const c = COPY[locale === "zh-TW" ? "zh-TW" : "en"];
  const report = computeResearchBlindSpots(sources, screenings, claims);

  const scoreState: RiskSeverity =
    report.robustnessScore >= 80 ? "ok" : report.robustnessScore >= 50 ? "warn" : "danger";

  const statusBadgeText = (severity: RiskSeverity, count: number): string => {
    if (severity === "ok") return c.statusHealthy;
    if (severity === "danger") return c.statusHighRisk(count);
    return c.statusCaution(count);
  };

  const quadrants: {
    key: string;
    title: string;
    desc: string;
    items: ResearchRecord[];
    severity: RiskSeverity;
    actionLabel: string;
    onAction: () => void;
  }[] = [
    {
      key: "abstract-only",
      title: c.qAbstractTitle,
      desc: c.qAbstractDesc,
      items: report.abstractOnlyClaims,
      severity: classifyQuadrantSeverity(report.abstractOnlyClaims.length, true),
      actionLabel: c.jumpEvidence,
      onAction: () => {
        const first = report.abstractOnlyClaims[0];
        onNavigate?.("evidence", first ? `record-${first.id}` : undefined);
      },
    },
    {
      key: "single-source",
      title: c.qSingleTitle,
      desc: c.qSingleDesc,
      items: report.singleSourceClaims,
      severity: classifyQuadrantSeverity(report.singleSourceClaims.length),
      actionLabel: c.jumpEvidence,
      onAction: () => {
        const first = report.singleSourceClaims[0];
        onNavigate?.("evidence", first ? `record-${first.id}` : undefined);
      },
    },
    {
      key: "uncited-included",
      title: c.qUncitedTitle,
      desc: c.qUncitedDesc,
      items: report.uncitedIncludedSources,
      severity: classifyQuadrantSeverity(report.uncitedIncludedSources.length),
      actionLabel: c.jumpLiterature,
      onAction: () => {
        const first = report.uncitedIncludedSources[0];
        if (first && onOpenPaper) onOpenPaper(first);
        else onNavigate?.("literature", first ? `record-${first.id}` : undefined);
      },
    },
    {
      key: "metadata-gaps",
      title: c.qMetaTitle,
      desc: c.qMetaDesc,
      items: report.metadataGapSources,
      severity: classifyQuadrantSeverity(report.metadataGapSources.length),
      actionLabel: c.jumpLiterature,
      onAction: () => {
        const first = report.metadataGapSources[0];
        if (first && onOpenPaper) onOpenPaper(first);
        else onNavigate?.("literature", first ? `record-${first.id}` : undefined);
      },
    },
  ];

  return (
    <section
      className={`vr-radar-panel${compact ? " is-compact" : ""}`}
      aria-label={c.radarTitle}
    >
      <header className="vr-radar-header">
        <div className="vr-radar-heading-text">
          <h3 className="vr-radar-title">{c.radarTitle}</h3>
          {!compact && <p className="vr-radar-sub">{c.radarSub}</p>}
        </div>
        <div className="vr-radar-health">
          <div className="vr-radar-health-top">
            <span className={`vr-led is-${scoreState}`} aria-hidden="true" />
            <span className="vr-radar-health-label">{c.robustnessLabel}</span>
            <strong className="vr-radar-health-score">{report.robustnessScore}%</strong>
          </div>
          <div className="vr-radar-health-bar" aria-hidden="true">
            <span
              className={`vr-radar-health-fill is-${scoreState}`}
              style={{ width: `${report.robustnessScore}%` }}
            />
          </div>
        </div>
      </header>

      <div className="vr-radar-grid">
        {quadrants.map((q) => (
          <article key={q.key} className={`vr-radar-card is-${q.severity}`}>
            <div className="vr-radar-card-top">
              <span className="vr-radar-card-title-wrap">
                <span className={`vr-led is-${q.severity}`} aria-hidden="true" />
                <h4 className="vr-radar-card-title">{q.title}</h4>
              </span>
              <span className={`vr-risk-badge is-${q.severity}`}>
                {statusBadgeText(q.severity, q.items.length)}
              </span>
            </div>

            {!compact && <p className="vr-radar-card-desc">{q.desc}</p>}

            {!compact && (
              <div className="vr-radar-preview">
                {q.items.length > 0 ? (
                  q.items.slice(0, 2).map((item) => (
                    <span key={item.id} className="vr-radar-item-chip">
                      {previewText(item)}
                    </span>
                  ))
                ) : (
                  <span className="vr-radar-clear-note">{c.allClearItem}</span>
                )}
              </div>
            )}

            {(onNavigate || onOpenPaper) && (
              <div className="vr-radar-card-footer">
                <button
                  type="button"
                  className="button secondary small vr-radar-jump-btn"
                  onClick={q.onAction}
                >
                  {q.actionLabel} <span aria-hidden="true">→</span>
                </button>
              </div>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
