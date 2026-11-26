export type ThemeMode = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "research-hub-theme";

function isThemeMode(value: unknown): value is ThemeMode {
  return value === "light" || value === "dark" || value === "system";
}

/**
 * Reads the persisted theme preference without writing to localStorage.
 * Defaults to "light" so unconfigured sessions and tests stay deterministic
 * and localStorage remains untouched on initial default render.
 */
export function readStoredTheme(): ThemeMode {
  try {
    if (typeof window === "undefined" || !window.localStorage) {
      return "light";
    }
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isThemeMode(raw) ? raw : "light";
  } catch {
    return "light";
  }
}

export function resolveThemeMode(mode: ThemeMode): ResolvedTheme {
  if (mode === "light" || mode === "dark") {
    return mode;
  }
  try {
    if (
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches
    ) {
      return "dark";
    }
  } catch {
    // Fall back to deterministic light mode when matchMedia is unavailable.
  }
  return "light";
}

/**
 * Applies the resolved theme to document.documentElement without touching localStorage.
 */
export function applyThemeToDocument(mode: ThemeMode): ResolvedTheme {
  const resolved = resolveThemeMode(mode);
  if (typeof document !== "undefined" && document.documentElement) {
    document.documentElement.dataset.theme = resolved;
    document.documentElement.dataset.themeMode = mode;
    document.documentElement.style.colorScheme = resolved;
  }
  return resolved;
}

/**
 * Persists user-chosen ThemeMode under "research-hub-theme" and applies it to the document.
 * Call ONLY on explicit user interaction (never on initial default render).
 */
export function persistAndApplyTheme(mode: ThemeMode): ResolvedTheme {
  try {
    if (typeof window !== "undefined" && window.localStorage) {
      window.localStorage.setItem(THEME_STORAGE_KEY, mode);
    }
  } catch {
    // Ignore storage quota or sandbox restrictions while still applying DOM theme.
  }
  return applyThemeToDocument(mode);
}

/**
 * Subscribes to OS prefers-color-scheme changes when mode === "system".
 */
export function subscribeSystemTheme(
  onSystemChange: (resolved: ResolvedTheme) => void,
): () => void {
  try {
    if (
      typeof window === "undefined" ||
      typeof window.matchMedia !== "function"
    ) {
      return () => {};
    }
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const listener = (event: MediaQueryListEvent) => {
      onSystemChange(event.matches ? "dark" : "light");
    };
    if (typeof mql.addEventListener === "function") {
      mql.addEventListener("change", listener);
      return () => mql.removeEventListener("change", listener);
    }
  } catch {
    // Ignore non-browser environments.
  }
  return () => {};
}
