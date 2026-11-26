import {
  persistAndApplyTheme,
  resolveThemeMode,
  type ThemeMode,
} from "./theme";

export interface ThemeQuickButtonLabels {
  light?: string;
  dark?: string;
  system?: string;
  switchToLight?: string;
  switchToDark?: string;
  title?: string;
}

export interface ThemeQuickButtonProps {
  mode: ThemeMode;
  onChange: (next: ThemeMode) => void;
  tLabels?: ThemeQuickButtonLabels;
  locale?: "en" | "zh-TW";
  tooltipPos?: "top" | "top-start" | "top-end" | "bottom-start" | "bottom-end";
}

export interface ThemeModeCardsLabels {
  groupLabel?: string;
  light?: string;
  lightDesc?: string;
  dark?: string;
  darkDesc?: string;
  system?: string;
  systemDesc?: string;
}

export interface ThemeModeCardsProps {
  mode: ThemeMode;
  onChange: (next: ThemeMode) => void;
  labels?: ThemeModeCardsLabels;
  locale?: "en" | "zh-TW";
}

function SunIcon() {
  return (
    <svg
      width={15}
      height={15}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.85}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <circle cx="12" cy="12" r="4.2" />
      <path d="M12 2.4v2.3M12 19.3v2.3M4.9 4.9l1.65 1.65M17.45 17.45l1.65 1.65M2.4 12h2.3M19.3 12h2.3M4.9 19.1l1.65-1.65M17.45 6.55l1.65-1.65" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg
      width={15}
      height={15}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.85}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M20.35 14.65A8.5 8.5 0 0 1 9.35 3.65a8.5 8.5 0 1 0 11 11Z" />
    </svg>
  );
}

/**
 * Compact Sun/Moon icon button for the sidebar footer.
 * Never touches localStorage on initial render; persists and applies on explicit click.
 */
export function ThemeQuickButton({
  mode,
  onChange,
  tLabels,
  locale = "en",
  tooltipPos = "top",
}: ThemeQuickButtonProps) {
  const resolved = resolveThemeMode(mode);
  const nextMode: ThemeMode = resolved === "dark" ? "light" : "dark";
  const isZh = locale === "zh-TW";

  const actionLabel =
    resolved === "dark"
      ? (tLabels?.switchToLight ??
        (tLabels?.light
          ? `${tLabels.title ? `${tLabels.title}: ` : ""}${tLabels.light}`
          : isZh
            ? "切換至淺色主題"
            : "Switch to light theme"))
      : (tLabels?.switchToDark ??
        (tLabels?.dark
          ? `${tLabels.title ? `${tLabels.title}: ` : ""}${tLabels.dark}`
          : isZh
            ? "切換至深色主題"
            : "Switch to dark theme"));

  return (
    <button
      type="button"
      className="button secondary icon-btn theme-quick-btn"
      aria-label={actionLabel}
      data-tooltip={actionLabel}
      data-tooltip-pos={tooltipPos}
      data-theme-resolved={resolved}
      onClick={() => {
        persistAndApplyTheme(nextMode);
        onChange(nextMode);
      }}
    >
      {resolved === "dark" ? <SunIcon /> : <MoonIcon />}
    </button>
  );
}

function ThemeMiniPreview({ variant }: { variant: ThemeMode }) {
  if (variant === "light") {
    return (
      <svg
        className="theme-mode-preview"
        viewBox="0 0 120 68"
        fill="none"
        aria-hidden="true"
        focusable="false"
      >
        <rect width="120" height="68" rx="6" fill="#f1f4f9" />
        <rect width="30" height="68" fill="#0e1522" />
        <circle cx="9" cy="10" r="2.2" fill="#38bdf8" />
        <rect x="6" y="18" width="18" height="3.5" rx="1.75" fill="#334155" />
        <rect x="6" y="25" width="15" height="3.5" rx="1.75" fill="#243652" />
        <rect x="37" y="9" width="75" height="22" rx="4" fill="#ffffff" stroke="#dbe2ee" />
        <rect x="43" y="15" width="32" height="4" rx="2" fill="#0f172a" />
        <rect x="43" y="22" width="52" height="3" rx="1.5" fill="#64748b" />
        <rect x="92" y="14" width="14" height="6" rx="3" fill="#0e5a72" />
        <rect x="37" y="36" width="35" height="23" rx="4" fill="#ffffff" stroke="#dbe2ee" />
        <rect x="77" y="36" width="35" height="23" rx="4" fill="#ffffff" stroke="#dbe2ee" />
        <rect x="43" y="43" width="20" height="3.5" rx="1.75" fill="#10925e" />
        <rect x="83" y="43" width="20" height="3.5" rx="1.75" fill="#2563eb" />
      </svg>
    );
  }

  if (variant === "dark") {
    return (
      <svg
        className="theme-mode-preview"
        viewBox="0 0 120 68"
        fill="none"
        aria-hidden="true"
        focusable="false"
      >
        <rect width="120" height="68" rx="6" fill="#0b111d" />
        <rect width="30" height="68" fill="#070c15" />
        <circle cx="9" cy="10" r="2.2" fill="#38bdf8" />
        <rect x="6" y="18" width="18" height="3.5" rx="1.75" fill="#1f2e47" />
        <rect x="6" y="25" width="15" height="3.5" rx="1.75" fill="#182437" />
        <rect x="37" y="9" width="75" height="22" rx="4" fill="#131d30" stroke="#24334a" />
        <rect x="43" y="15" width="32" height="4" rx="2" fill="#e7eef8" />
        <rect x="43" y="22" width="52" height="3" rx="1.5" fill="#98a8c0" />
        <rect x="92" y="14" width="14" height="6" rx="3" fill="#38bdf8" />
        <rect x="37" y="36" width="35" height="23" rx="4" fill="#131d30" stroke="#24334a" />
        <rect x="77" y="36" width="35" height="23" rx="4" fill="#131d30" stroke="#24334a" />
        <rect x="43" y="43" width="20" height="3.5" rx="1.75" fill="#34d399" />
        <rect x="83" y="43" width="20" height="3.5" rx="1.75" fill="#60a5fa" />
      </svg>
    );
  }

  return (
    <svg
      className="theme-mode-preview"
      viewBox="0 0 120 68"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <rect width="60" height="68" fill="#f1f4f9" />
      <rect x="60" width="60" height="68" fill="#0b111d" />
      <rect width="24" height="68" fill="#0e1522" />
      <circle cx="8" cy="10" r="2.2" fill="#38bdf8" />
      <rect x="5" y="18" width="14" height="3.5" rx="1.75" fill="#243652" />
      {/* Light left half */}
      <rect x="30" y="10" width="26" height="21" rx="3.5" fill="#ffffff" stroke="#dbe2ee" />
      <rect x="34" y="16" width="16" height="3.5" rx="1.75" fill="#0f172a" />
      <rect x="30" y="36" width="26" height="22" rx="3.5" fill="#ffffff" stroke="#dbe2ee" />
      <rect x="34" y="43" width="15" height="3.5" rx="1.75" fill="#0e5a72" />
      {/* Dark right half */}
      <rect x="64" y="10" width="48" height="21" rx="3.5" fill="#131d30" stroke="#24334a" />
      <rect x="70" y="16" width="24" height="3.5" rx="1.75" fill="#e7eef8" />
      <rect x="96" y="15" width="11" height="5.5" rx="2.75" fill="#38bdf8" />
      <rect x="64" y="36" width="48" height="22" rx="3.5" fill="#131d30" stroke="#24334a" />
      <rect x="70" y="43" width="22" height="3.5" rx="1.75" fill="#34d399" />
      <line x1="60" y1="0" x2="60" y2="68" stroke="#64748b" strokeOpacity="0.45" />
    </svg>
  );
}

/**
 * Three visual mini-preview radio cards (Light / Dark / System) using button[role="radio"].
 * Never renders a <select> combobox so existing combobox queries remain unambiguous.
 */
export function ThemeModeCards({
  mode,
  onChange,
  labels,
  locale = "en",
}: ThemeModeCardsProps) {
  const isZh = locale === "zh-TW";
  const groupLabel =
    labels?.groupLabel ?? (isZh ? "外觀主題模式" : "Appearance theme");

  const options: { id: ThemeMode; title: string; desc: string }[] = [
    {
      id: "light",
      title: labels?.light ?? (isZh ? "淺色" : "Light"),
      desc: labels?.lightDesc ?? (isZh ? "日間紙本對比" : "Archival daylight"),
    },
    {
      id: "dark",
      title: labels?.dark ?? (isZh ? "深色" : "Dark"),
      desc: labels?.darkDesc ?? (isZh ? "深色石板工作台" : "Deep slate"),
    },
    {
      id: "system",
      title: labels?.system ?? (isZh ? "跟隨系統" : "System"),
      desc: labels?.systemDesc ?? (isZh ? "自動同步系統外觀" : "Match OS setting"),
    },
  ];

  return (
    <div
      role="radiogroup"
      aria-label={groupLabel}
      className="theme-mode-cards"
    >
      {options.map((opt) => {
        const checked = mode === opt.id;
        return (
          <button
            key={opt.id}
            type="button"
            role="radio"
            aria-checked={checked}
            data-theme-option={opt.id}
            className={`theme-mode-card${checked ? " is-active" : ""}`}
            onClick={() => {
              persistAndApplyTheme(opt.id);
              onChange(opt.id);
            }}
          >
            <ThemeMiniPreview variant={opt.id} />
            <span className="theme-mode-card-meta">
              <span className="theme-mode-card-title">
                <span className="theme-mode-radio-dot" aria-hidden="true" />
                <span>{opt.title}</span>
              </span>
              <span className="theme-mode-card-desc">{opt.desc}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
