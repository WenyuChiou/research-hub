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

/** Faceted crystal polygon mark representing Obsidian Vault. */
export function ObsidianIcon({ size = 15 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M12.6 2.2 6.2 7.1l-2.1 7.8 5.7 6.9 7.8-2.3 2.3-8.6-7.3-8.7Z"
        fill="currentColor"
        fillOpacity="0.14"
        stroke="currentColor"
        strokeWidth="1.85"
        strokeLinejoin="round"
      />
      <path
        d="M12.6 2.2 10.4 10l7.2 9.5M10.4 10l-6.3 4.9M10.4 10l9.5.9"
        stroke="currentColor"
        strokeWidth="1.55"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Framed archival Z monogram representing Zotero reference library. */
export function ZoteroIcon({ size = 15 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <rect
        x="3.2"
        y="3.2"
        width="17.6"
        height="17.6"
        rx="4.2"
        fill="currentColor"
        fillOpacity="0.11"
        stroke="currentColor"
        strokeWidth="1.8"
      />
      <path
        d="M8.2 7.6h7.6L8.2 16.4h7.6"
        stroke="currentColor"
        strokeWidth="2.1"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Grounded notebook + synthesis wave mark representing NotebookLM. */
export function NotebookLmIcon({ size = 15 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <rect
        x="3.5"
        y="3"
        width="17"
        height="18"
        rx="3.6"
        fill="currentColor"
        fillOpacity="0.11"
        stroke="currentColor"
        strokeWidth="1.8"
      />
      <path
        d="M7.5 3.5v17"
        stroke="currentColor"
        strokeWidth="1.55"
        strokeOpacity="0.7"
      />
      <path
        d="M10.6 14.6c.9-2.8 2.3-4.2 3.8-4.2 1.4 0 2.3 1.3 3.2 4.2"
        stroke="currentColor"
        strokeWidth="1.85"
        strokeLinecap="round"
      />
      <path
        d="M11.6 9.2c.8-.9 1.7-1.3 2.7-1.3s1.9.4 2.7 1.3"
        stroke="currentColor"
        strokeWidth="1.55"
        strokeLinecap="round"
      />
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
