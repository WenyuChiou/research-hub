import { useId } from "react";
import type { DestinationState } from "./AgentHandoffModal";

export type BrandDestination = "obsidian" | "zotero" | "notebooklm";

export type LabelTone =
  | "blue"
  | "teal"
  | "emerald"
  | "indigo"
  | "plum"
  | "amber"
  | "coral"
  | "cyan"
  | "slate";

export type StatusLedState = "ok" | "configured" | "warn" | "error" | "idle";

export interface StatusLedProps {
  state: StatusLedState;
  label?: string;
  pulse?: boolean;
  className?: string;
}

const TONE_PALETTE: Exclude<LabelTone, "slate">[] = [
  "blue",
  "teal",
  "emerald",
  "indigo",
  "plum",
  "amber",
  "coral",
  "cyan",
];

const KEYWORD_TONES: [RegExp, LabelTone][] = [
  [
    /(bias|risk|limit|caveat|hallucinat|error|hazard|ethic|threat|fragil|偏誤|風險|限制|幻覺)/i,
    "coral",
  ],
  [
    /(hydrolog|water|river|flood|drought|basin|climate|ecolog|environ|水文|水資源|河川|乾旱|氣候)/i,
    "cyan",
  ],
  [
    /(benchmark|eval|metric|validat|calibrat|baseline|ablation|reproduc|基準|評測|驗證|校準)/i,
    "indigo",
  ],
  [
    /(human|cogniti|behavio|social|psycholog|persona|survey|interview|crowd|participant|人類|行為|社會|心理|受試)/i,
    "plum",
  ],
  [
    /(review|synthes|meta-analys|taxonomy|overview|policy|govern|econom|market|綜述|回顧|政策|治理|經濟)/i,
    "amber",
  ],
  [
    /(empiric|experiment|dataset|corpus|field|observat|clinical|trial|open-source|實證|實驗|資料集)/i,
    "emerald",
  ],
  [
    /(simulat|abm|agent-based|model|system|workflow|pipeline|framework|twin|模擬|系統|框架)/i,
    "teal",
  ],
  [
    /(llm|gpt|agent|multi-agent|prompt|rag|memory|reason|language-model|代理|多代理|推理|語言模型)/i,
    "blue",
  ],
];

function useSvgIdPrefix(prefix: string): string {
  const raw = useId();
  return `${prefix}-${raw.replace(/[^a-zA-Z0-9_-]/g, "_")}`;
}

/**
 * Deterministic GitHub-Issues / Primer style semantic tone classifier.
 * Maps common research semantics (method, domain, benchmark, caveat, human) to
 * curated archival hues and hashes arbitrary custom tags deterministically.
 */
export function classifyLabelTone(raw: string): LabelTone {
  const cleaned = raw.trim().replace(/^#+/, "").trim().toLocaleLowerCase();
  if (!cleaned || cleaned === "__unclassified__" || cleaned === "unclassified") {
    return "slate";
  }
  for (const [pattern, tone] of KEYWORD_TONES) {
    if (pattern.test(cleaned)) return tone;
  }
  let hash = 2166136261;
  for (let i = 0; i < cleaned.length; i++) {
    hash ^= cleaned.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return TONE_PALETTE[(hash >>> 0) % TONE_PALETTE.length];
}

/**
 * Parses optional GitHub-style scoped labels such as `method:benchmark` or `domain:hydrology`.
 */
export function splitScopedLabel(raw: string): { prefix: string | null; value: string } {
  const cleaned = raw.trim().replace(/^#+/, "").trim();
  const match = cleaned.match(/^([^:：]{1,24})[:：](.+)$/);
  if (match) {
    const prefix = match[1].trim();
    const value = match[2].trim();
    if (prefix && value) return { prefix, value };
  }
  return { prefix: null, value: cleaned };
}

export function GitHubLabelText({ label }: { label: string }) {
  const parsed = splitScopedLabel(label);
  if (parsed.prefix) {
    return (
      <>
        <span className="gh-label-dot" aria-hidden="true" />
        <span className="gh-label-scope">#{parsed.prefix}</span>
        <span className="gh-label-sep">:</span>
        <span className="gh-label-value">{parsed.value}</span>
      </>
    );
  }
  return (
    <>
      <span className="gh-label-dot" aria-hidden="true" />
      <span className="gh-label-value">#{parsed.value}</span>
    </>
  );
}

/**
 * High-definition multi-faceted amethyst crystal gemstone mark for Obsidian.
 * Uses unique per-instance SVG gradient IDs so multiple icons never collide.
 */
export function ObsidianIcon({ size = 15 }: { size?: number }) {
  const uid = useSvgIdPrefix("obs");
  const coreId = `${uid}-core`;
  const crownId = `${uid}-crown`;
  const baseId = `${uid}-base`;
  const rightId = `${uid}-right`;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id={coreId} x1="8" y1="3" x2="17.5" y2="20.5" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#9966ff" />
          <stop offset="52%" stopColor="#6c31e3" />
          <stop offset="100%" stopColor="#4a1fb8" />
        </linearGradient>
        <linearGradient id={crownId} x1="6" y1="2.2" x2="12.8" y2="11" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#c4b5fd" />
          <stop offset="100%" stopColor="#9966ff" />
        </linearGradient>
        <linearGradient id={baseId} x1="4.2" y1="10.2" x2="12.5" y2="22" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#6c31e3" />
          <stop offset="100%" stopColor="#4a1fb8" />
        </linearGradient>
        <linearGradient id={rightId} x1="13" y1="3.5" x2="20" y2="18.8" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#a78bfa" />
          <stop offset="55%" stopColor="#6c31e3" />
          <stop offset="100%" stopColor="#3b1590" />
        </linearGradient>
      </defs>
      {/* Upper-left illuminated crown facet */}
      <path d="M12.9 1.75 6.05 6.95 10.15 9.85 12.9 1.75Z" fill={`url(#${crownId})`} />
      {/* Upper-right shoulder facet */}
      <path d="M12.9 1.75 10.15 9.85 19.65 11.2 18.2 5.75 12.9 1.75Z" fill={`url(#${rightId})`} />
      {/* Left dark amethyst flank */}
      <path d="M6.05 6.95 3.95 14.75 9.95 22.2 10.15 9.85 6.05 6.95Z" fill={`url(#${baseId})`} />
      {/* Central brilliant amethyst table facet */}
      <path d="M10.15 9.85 9.95 22.2 17.55 19.35 19.65 11.2 10.15 9.85Z" fill={`url(#${coreId})`} />
      {/* Lower-right specular bevel */}
      <path d="M19.65 11.2 17.55 19.35 9.95 22.2 15.1 14.3 19.65 11.2Z" fill="#4a1fb8" fillOpacity="0.48" />
      {/* Crisp specular facet ridges for 15px-36px sharpness in Light & Dark themes */}
      <path
        d="M12.9 1.75 6.05 6.95 3.95 14.75 9.95 22.2 17.55 19.35 19.65 11.2 18.2 5.75 12.9 1.75Z"
        stroke="#c4b5fd"
        strokeOpacity="0.55"
        strokeWidth="0.6"
        strokeLinejoin="round"
      />
      <path
        d="M12.9 1.75 10.15 9.85M10.15 9.85 6.05 6.95M10.15 9.85 19.65 11.2M10.15 9.85 9.95 22.2"
        stroke="#ede9fe"
        strokeOpacity="0.52"
        strokeWidth="0.55"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * High-definition Zotero crimson isometric hexagon emblem with bold geometric white Z.
 */
export function ZoteroIcon({ size = 15 }: { size?: number }) {
  const uid = useSvgIdPrefix("zot");
  const bgId = `${uid}-bg`;
  const facetId = `${uid}-facet`;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id={bgId} x1="4" y1="2" x2="20" y2="22" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#e03c4a" />
          <stop offset="55%" stopColor="#cc2936" />
          <stop offset="100%" stopColor="#9e1b26" />
        </linearGradient>
        <linearGradient id={facetId} x1="12" y1="2" x2="21" y2="18" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#ff6b78" stopOpacity="0.32" />
          <stop offset="100%" stopColor="#7f131d" stopOpacity="0.28" />
        </linearGradient>
      </defs>
      {/* Rounded isometric hexagon badge */}
      <path
        d="M10.9 2.15a2.3 2.3 0 0 1 2.2 0l6.65 3.72a2.3 2.3 0 0 1 1.18 2v8.26a2.3 2.3 0 0 1-1.18 2l-6.65 3.72a2.3 2.3 0 0 1-2.2 0l-6.65-3.72a2.3 2.3 0 0 1-1.18-2V7.87a2.3 2.3 0 0 1 1.18-2l6.65-3.72Z"
        fill={`url(#${bgId})`}
      />
      {/* Subtle right-half isometric facet depth */}
      <path
        d="M12 1.85v20.3l7.75-4.32a2.2 2.2 0 0 0 1.18-1.96V8.13a2.2 2.2 0 0 0-1.18-1.96L12 1.85Z"
        fill={`url(#${facetId})`}
      />
      <path
        d="M10.9 2.15a2.3 2.3 0 0 1 2.2 0l6.65 3.72a2.3 2.3 0 0 1 1.18 2v8.26a2.3 2.3 0 0 1-1.18 2l-6.65 3.72a2.3 2.3 0 0 1-2.2 0l-6.65-3.72a2.3 2.3 0 0 1-1.18-2V7.87a2.3 2.3 0 0 1 1.18-2l6.65-3.72Z"
        stroke="#fda4af"
        strokeOpacity="0.42"
        strokeWidth="0.65"
      />
      {/* Crisp bold geometric Z */}
      <path
        d="M7.65 7.35h8.7v2.18l-5.62 5.02h5.72v2.18H7.55v-2.16l5.64-5.04H7.65V7.35Z"
        fill="#ffffff"
      />
    </svg>
  );
}

/**
 * High-definition Google NotebookLM dark iridescent badge with multi-wave synthesis arcs.
 */
export function NotebookLmIcon({ size = 15 }: { size?: number }) {
  const uid = useSvgIdPrefix("nlm");
  const tileId = `${uid}-tile`;
  const outerWaveId = `${uid}-wave-outer`;
  const midWaveId = `${uid}-wave-mid`;
  const innerWaveId = `${uid}-wave-inner`;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id={tileId} x1="3" y1="2" x2="21" y2="22" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#1e293b" />
          <stop offset="100%" stopColor="#0b1120" />
        </linearGradient>
        <linearGradient id={outerWaveId} x1="4.5" y1="17" x2="19.5" y2="7" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#3b82f6" />
          <stop offset="50%" stopColor="#10b981" />
          <stop offset="100%" stopColor="#a855f7" />
        </linearGradient>
        <linearGradient id={midWaveId} x1="6.8" y1="17.2" x2="17.2" y2="10.2" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#60a5fa" />
          <stop offset="55%" stopColor="#34d399" />
          <stop offset="100%" stopColor="#c084fc" />
        </linearGradient>
        <linearGradient id={innerWaveId} x1="9.2" y1="17.4" x2="14.8" y2="13.5" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#93c5fd" />
          <stop offset="100%" stopColor="#e9d5ff" />
        </linearGradient>
      </defs>
      <rect
        x="1.75"
        y="1.75"
        width="20.5"
        height="20.5"
        rx="5.4"
        fill={`url(#${tileId})`}
        stroke="#64748b"
        strokeOpacity="0.55"
        strokeWidth="0.85"
      />
      {/* Concentric NotebookLM synthesis / acoustic arcs */}
      <path
        d="M5.15 16.85a6.85 6.85 0 0 1 13.7 0"
        stroke={`url(#${outerWaveId})`}
        strokeWidth="2.15"
        strokeLinecap="round"
      />
      <path
        d="M8.05 16.85a3.95 3.95 0 0 1 7.9 0"
        stroke={`url(#${midWaveId})`}
        strokeWidth="2.05"
        strokeLinecap="round"
      />
      <path
        d="M10.8 16.85a1.2 1.2 0 0 1 2.4 0"
        stroke={`url(#${innerWaveId})`}
        strokeWidth="2.05"
        strokeLinecap="round"
      />
    </svg>
  );
}

/**
 * High-definition BibTeX / Overleaf emerald-teal curly-brace citation badge.
 */
export function BibtexIcon({ size = 16 }: { size?: number }) {
  const uid = useSvgIdPrefix("bib");
  const bgId = `${uid}-bg`;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id={bgId} x1="2.5" y1="2" x2="21.5" y2="22" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#10b981" />
          <stop offset="100%" stopColor="#0f766e" />
        </linearGradient>
      </defs>
      <rect
        x="2"
        y="2"
        width="20"
        height="20"
        rx="5"
        fill={`url(#${bgId})`}
        stroke="#6ee7b7"
        strokeOpacity="0.45"
        strokeWidth="0.7"
      />
      <path
        d="M8.6 7.2c-1.15 0-1.65.55-1.65 1.55v1.55c0 .85-.45 1.35-1.3 1.7.85.35 1.3.85 1.3 1.7v1.55c0 1 .5 1.55 1.65 1.55M15.4 7.2c1.15 0 1.65.55 1.65 1.55v1.55c0 .85.45 1.35 1.3 1.7-.85.35-1.3.85-1.3 1.7v1.55c0 1-.5 1.55-1.65 1.55"
        stroke="#ffffff"
        strokeWidth="1.85"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="12" r="1.65" fill="#d1fae5" />
    </svg>
  );
}

/**
 * High-definition RIS / EndNote structured reference record emblem.
 */
export function RisEndnoteIcon({ size = 16 }: { size?: number }) {
  const uid = useSvgIdPrefix("ris");
  const bgId = `${uid}-bg`;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id={bgId} x1="3" y1="2" x2="21" y2="22" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#3b82f6" />
          <stop offset="100%" stopColor="#1d4ed8" />
        </linearGradient>
      </defs>
      <path
        d="M5.5 2.5h9.2L19.5 7.3v12.2a2 2 0 0 1-2 2h-12a2 2 0 0 1-2-2V4.5a2 2 0 0 1 2-2Z"
        fill={`url(#${bgId})`}
        stroke="#93c5fd"
        strokeOpacity="0.48"
        strokeWidth="0.7"
      />
      <path d="M14.5 2.6v4.9h4.9" fill="#1e3a8a" fillOpacity="0.45" />
      <path
        d="M14.5 2.8v4.5h4.5"
        stroke="#dbeafe"
        strokeOpacity="0.75"
        strokeWidth="1.1"
        strokeLinejoin="round"
      />
      {/* Structured TY / AU / DO tagged lines */}
      <path
        d="M6.8 10.6h2.2M10.8 10.6h5.4M6.8 13.8h2.2M10.8 13.8h5.4M6.8 17h2.2M10.8 17h3.8"
        stroke="#ffffff"
        strokeWidth="1.65"
        strokeLinecap="round"
      />
      <circle cx="16.8" cy="17" r="1.15" fill="#fbbf24" />
    </svg>
  );
}

/**
 * High-definition CSL-JSON / Quarto structured citation schema emblem.
 */
export function CslJsonIcon({ size = 16 }: { size?: number }) {
  const uid = useSvgIdPrefix("csl");
  const bgId = `${uid}-bg`;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id={bgId} x1="2.5" y1="2" x2="21.5" y2="22" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#6366f1" />
          <stop offset="100%" stopColor="#0284c7" />
        </linearGradient>
      </defs>
      <rect
        x="2"
        y="2"
        width="20"
        height="20"
        rx="5"
        fill={`url(#${bgId})`}
        stroke="#bae6fd"
        strokeOpacity="0.48"
        strokeWidth="0.7"
      />
      <path
        d="M8.8 7.2H6.6v9.6h2.2M15.2 7.2h2.2v9.6h-2.2"
        stroke="#ffffff"
        strokeWidth="1.85"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="10.1" r="1.25" fill="#e0f2fe" />
      <circle cx="12" cy="14.1" r="1.25" fill="#7dd3fc" />
    </svg>
  );
}

export function BrandMark({
  brand,
  size = 15,
}: {
  brand: BrandDestination;
  size?: number;
}) {
  if (brand === "obsidian") return <ObsidianIcon size={size} />;
  if (brand === "zotero") return <ZoteroIcon size={size} />;
  return <NotebookLmIcon size={size} />;
}

/**
 * Reusable glowing LED indicator dot for integration, pipeline, and runtime states.
 */
export function StatusLed({
  state,
  label,
  pulse = false,
  className,
}: StatusLedProps) {
  const classes = [
    "status-led",
    `is-${state}`,
    pulse ? "is-pulse" : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <span
      className={classes}
      data-state={state}
      aria-hidden={!label}
      role={label ? "status" : undefined}
      aria-label={label || undefined}
      title={label || undefined}
    />
  );
}

const BRAND_NAMES: Record<BrandDestination, string> = {
  obsidian: "Obsidian",
  zotero: "Zotero",
  notebooklm: "NotebookLM",
};

/**
 * Icon-only destination status badge for Obsidian, Zotero, and NotebookLM.
 * Removes visual text clutter while preserving full ARIA & hover tooltip clarity.
 */
export function DestinationBrandChip({
  brand,
  state,
  statusText,
  tooltipPos = "bottom-end",
  onClick,
}: {
  brand: BrandDestination;
  state: DestinationState;
  statusText: string;
  tooltipPos?: "top" | "top-start" | "top-end" | "bottom-start" | "bottom-end";
  onClick?: () => void;
}) {
  const brandName = BRAND_NAMES[brand];
  const fullLabel = `${brandName} · ${statusText}`;
  const className = `pipeline-icon-chip is-${state} brand-${brand}${onClick ? " icon-btn" : ""}`;

  if (onClick) {
    return (
      <button
        type="button"
        className={className}
        aria-label={fullLabel}
        data-tooltip={fullLabel}
        data-tooltip-pos={tooltipPos}
        onClick={onClick}
      >
        <BrandMark brand={brand} size={15} />
        <span className="pipeline-icon-dot" aria-hidden="true" />
      </button>
    );
  }

  return (
    <span
      role="img"
      tabIndex={0}
      className={className}
      title={fullLabel}
      aria-label={fullLabel}
      data-tooltip={fullLabel}
      data-tooltip-pos={tooltipPos}
    >
      <BrandMark brand={brand} size={15} />
      <span className="pipeline-icon-dot" aria-hidden="true" />
    </span>
  );
}
