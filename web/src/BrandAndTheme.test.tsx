import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import {
  BibtexIcon,
  BrandMark,
  CslJsonIcon,
  RisEndnoteIcon,
  StatusLed,
} from "./BrandIcons";
import {
  applyThemeToDocument,
  persistAndApplyTheme,
  readStoredTheme,
  THEME_STORAGE_KEY,
  type ThemeMode,
} from "./theme";
import { ThemeModeCards, ThemeQuickButton } from "./ThemeToggle";
import tokensCss from "./tokens.css?raw";

function parseSelectorStyle(cssText: string, selector: string): CSSStyleDeclaration {
  const styleEl = document.createElement("style");
  styleEl.textContent = cssText;
  document.head.append(styleEl);
  try {
    for (const rule of Array.from(styleEl.sheet!.cssRules)) {
      if (rule.type === CSSRule.STYLE_RULE) {
        const styleRule = rule as CSSStyleRule;
        const selectors = styleRule.selectorText.split(",").map((s) => s.trim());
        if (selectors.includes(selector)) {
          return styleRule.style;
        }
      }
    }
    throw new Error(`Selector ${selector} not found in tokens.css`);
  } finally {
    styleEl.remove();
  }
}

function relativeLuminance(hex: string): number {
  expect(hex).toMatch(/^#[0-9a-fA-F]{6}$/);
  return [1, 3, 5]
    .map((start) => Number.parseInt(hex.slice(start, start + 2), 16) / 255)
    .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
    .reduce((acc, val, idx) => acc + val * [0.2126, 0.7152, 0.0722][idx], 0);
}

function wcagContrast(fgHex: string, bgHex: string): number {
  const [low, high] = [relativeLuminance(fgHex), relativeLuminance(bgHex)].sort(
    (a, b) => a - b,
  );
  return (high + 0.05) / (low + 0.05);
}

afterEach(() => {
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
  delete document.documentElement.dataset.themeMode;
  document.documentElement.style.colorScheme = "";
  vi.unstubAllGlobals();
});

describe("HD BrandIcons, Citation Format Icons, and StatusLed", () => {
  it("generates unique non-colliding SVG linearGradient IDs across multiple BrandMark instances", () => {
    const { container } = render(
      <div>
        <BrandMark brand="obsidian" size={15} />
        <BrandMark brand="obsidian" size={28} />
        <BrandMark brand="zotero" size={20} />
        <BrandMark brand="zotero" size={36} />
        <BrandMark brand="notebooklm" size={15} />
        <BrandMark brand="notebooklm" size={28} />
      </div>,
    );

    const svgs = container.querySelectorAll("svg");
    expect(svgs).toHaveLength(6);

    const gradients = Array.from(container.querySelectorAll("linearGradient"));
    expect(gradients.length).toBeGreaterThanOrEqual(12);

    const ids = gradients.map((g) => g.getAttribute("id")).filter(Boolean) as string[];
    expect(ids).toHaveLength(gradients.length);
    expect(new Set(ids).size).toBe(ids.length);

    // Every url(#...) paint reference resolves to a gradient defined in the document
    const paintRefs = Array.from(container.querySelectorAll("svg *"))
      .flatMap((el) => [el.getAttribute("fill"), el.getAttribute("stroke")])
      .filter((val): val is string => Boolean(val && val.startsWith("url(#")))
      .map((val) => val.match(/^url\(#([^)]+)\)$/)?.[1])
      .filter(Boolean) as string[];
    expect(paintRefs.length).toBeGreaterThanOrEqual(10);
    for (const refId of paintRefs) {
      expect(ids).toContain(refId);
    }

    // Zero text clutter inside decorative SVGs so icon-only buttons keep empty textContent
    for (const svg of Array.from(svgs)) {
      expect(svg.textContent).toBe("");
      expect(svg).toHaveAttribute("aria-hidden", "true");
    }
  });

  it("renders crisp HD BibtexIcon, RisEndnoteIcon, and CslJsonIcon with unique gradient IDs", () => {
    const { container } = render(
      <div>
        <BibtexIcon size={18} />
        <BibtexIcon size={24} />
        <RisEndnoteIcon size={18} />
        <RisEndnoteIcon size={24} />
        <CslJsonIcon size={18} />
        <CslJsonIcon size={24} />
      </div>,
    );

    const svgs = container.querySelectorAll("svg");
    expect(svgs).toHaveLength(6);
    const gradientIds = Array.from(container.querySelectorAll("linearGradient")).map((el) =>
      el.getAttribute("id"),
    );
    expect(gradientIds).toHaveLength(6);
    expect(new Set(gradientIds).size).toBe(6);
  });

  it("renders StatusLed with accessible status semantics when labeled and aria-hidden when decorative", () => {
    const { container, rerender } = render(<StatusLed state="idle" />);
    const dot = container.querySelector(".status-led")!;
    expect(dot).toHaveClass("status-led", "is-idle");
    expect(dot).toHaveAttribute("aria-hidden", "true");
    expect(dot).not.toHaveAttribute("role");

    rerender(<StatusLed state="ok" label="Zotero connected" pulse />);
    const liveStatus = screen.getByRole("status", { name: "Zotero connected" });
    expect(liveStatus).toHaveClass("status-led", "is-ok", "is-pulse");
    expect(liveStatus).toHaveAttribute("aria-hidden", "false");

    for (const state of ["configured", "warn", "error"] as const) {
      rerender(<StatusLed state={state} label={`State ${state}`} />);
      expect(screen.getByRole("status", { name: `State ${state}` })).toHaveClass(
        `is-${state}`,
      );
    }
  });
});

describe("Theme Engine, ThemeQuickButton, and ThemeModeCards", () => {
  it("defaults to light without writing localStorage on initial render and updates localStorage + dataset.theme on click", async () => {
    const user = userEvent.setup();

    expect(readStoredTheme()).toBe("light");
    expect(window.localStorage.length).toBe(0);

    function Harness() {
      const [mode, setMode] = useState<ThemeMode>(() => {
        const initial = readStoredTheme();
        applyThemeToDocument(initial);
        return initial;
      });
      return (
        <div>
          <ThemeQuickButton mode={mode} onChange={setMode} locale="en" />
          <ThemeModeCards mode={mode} onChange={setMode} locale="en" />
        </div>
      );
    }

    render(<Harness />);

    // Initial render MUST leave localStorage untouched!
    expect(window.localStorage.length).toBe(0);
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
    expect(document.documentElement.dataset.theme).toBe("light");

    // Zero <select> comboboxes rendered by ThemeToggle
    expect(screen.queryAllByRole("combobox")).toHaveLength(0);

    // Click sidebar quick button -> switches to dark and writes localStorage
    const quickBtn = screen.getByRole("button", { name: /switch to dark theme/i });
    expect(quickBtn).toHaveClass("button", "secondary", "icon-btn", "theme-quick-btn");
    expect(quickBtn).toHaveAttribute("data-tooltip");
    await user.click(quickBtn);

    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(screen.getByRole("radio", { name: /Dark/i })).toHaveAttribute(
      "aria-checked",
      "true",
    );

    // Click System radio card with mocked dark OS preference
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockImplementation((query: string) => ({
        matches: query === "(prefers-color-scheme: dark)",
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
    await user.click(screen.getByRole("radio", { name: /System/i }));
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("system");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(document.documentElement.dataset.themeMode).toBe("system");

    // Click Light radio card -> switches back to light
    await user.click(screen.getByRole("radio", { name: /Light/i }));
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    expect(document.documentElement.dataset.theme).toBe("light");

    // Explicit helper verification
    expect(persistAndApplyTheme("dark")).toBe("dark");
    expect(readStoredTheme()).toBe("dark");
  });

  it("achieves WCAG AA >= 4.5:1 foreground/background contrast across all dark-mode surfaces, scopes, and semantic labels", () => {
    const darkStyle = parseSelectorStyle(tokensCss, ':root[data-theme="dark"]');
    const token = (name: string) => darkStyle.getPropertyValue(name).trim();

    const surfaces = [
      token("--paper"),
      token("--surface-tint"),
      token("--white"),
      token("--wash"),
    ];
    for (const bg of surfaces) {
      expect(wcagContrast(token("--ink"), bg), `--ink on ${bg}`).toBeGreaterThanOrEqual(4.5);
      expect(wcagContrast(token("--muted"), bg), `--muted on ${bg}`).toBeGreaterThanOrEqual(4.5);
      expect(wcagContrast(token("--teal"), bg), `--teal on ${bg}`).toBeGreaterThanOrEqual(4.5);
      expect(wcagContrast(token("--focus"), bg), `--focus on ${bg}`).toBeGreaterThanOrEqual(3.0);
    }

    // Dark IDE rail contrast invariants
    expect(wcagContrast(token("--ide-fg"), token("--ide-bg"))).toBeGreaterThanOrEqual(4.5);
    expect(wcagContrast(token("--ide-muted"), token("--ide-bg"))).toBeGreaterThanOrEqual(4.5);
    expect(wcagContrast(token("--ide-muted"), token("--ide-surface"))).toBeGreaterThanOrEqual(4.5);
    expect(wcagContrast(token("--ide-border-strong"), token("--ide-surface"))).toBeGreaterThanOrEqual(3.0);

    // Reading scope tokens in dark mode
    for (const scope of ["full", "abstract", "meta", "unknown"]) {
      expect(
        wcagContrast(token(`--scope-${scope}-fg`), token(`--scope-${scope}-bg`)),
        `dark scope-${scope}`,
      ).toBeGreaterThanOrEqual(4.5);
    }

    // Default tag + all 9 GitHub-Primer semantic label families in dark mode
    expect(wcagContrast(token("--tag-fg"), token("--tag-bg"))).toBeGreaterThanOrEqual(4.5);
    for (const family of [
      "blue",
      "teal",
      "emerald",
      "indigo",
      "plum",
      "amber",
      "coral",
      "cyan",
      "slate",
    ]) {
      expect(
        wcagContrast(token(`--lbl-${family}-fg`), token(`--lbl-${family}-bg`)),
        `dark lbl-${family}`,
      ).toBeGreaterThanOrEqual(4.5);
    }

    // Ensure status-led rules exist in tokens.css and no transition: all exists
    expect(tokensCss).toContain(".status-led.is-ok");
    expect(tokensCss).toContain(".status-led.is-configured");
    expect(tokensCss).toContain(".status-led.is-warn");
    expect(tokensCss).toContain(".status-led.is-error");
    expect(tokensCss).toContain(".status-led.is-idle");
    expect(tokensCss).not.toMatch(/transition\s*:\s*all\b/i);
  });
});
