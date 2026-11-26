import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Field } from "./components";
import tokens from "./tokens.css?raw";
import styles from "./styles.css?raw";
import libraryCss from "./library.css?raw";

// Source/cascade guardrails, NOT measured layout or actual browser zoom.
// jsdom cannot measure glyphs, rendered overflow, or browser zoom.
function parseRules(source: string) {
  const element = document.createElement("style");
  element.textContent = source.replace(/@import[^;]+;/g, "");
  document.head.append(element);
  const rules: {
    selectors: string[];
    style: CSSStyleDeclaration;
    media: string;
  }[] = [];
  function visit(list: CSSRuleList, media = "") {
    for (const rule of Array.from(list)) {
      if (rule.type === CSSRule.STYLE_RULE) {
        const styleRule = rule as CSSStyleRule;
        rules.push({
          selectors: styleRule.selectorText
            .split(",")
            .map((value) => value.trim()),
          style: styleRule.style,
          media,
        });
      } else if (rule.type === CSSRule.MEDIA_RULE) {
        const mediaRule = rule as CSSMediaRule;
        visit(mediaRule.cssRules, mediaRule.conditionText);
      }
    }
  }
  visit(element.sheet!.cssRules);
  element.remove();
  return rules;
}
const rules = parseRules(styles);
const libraryRules = parseRules(libraryCss);
const combinedRules = [...rules, ...libraryRules];
const theme = parseRules(tokens)[0].style;
function values(selector: string, property: string, media?: string) {
  return rules
    .filter(
      (rule) =>
        rule.selectors.includes(selector) &&
        (media === undefined || rule.media === media),
    )
    .map((rule) => rule.style.getPropertyValue(property).trim())
    .filter((value) => Boolean(value) && value !== "inherit");
}
function resolve(value: string) {
  return value.replace(/var\((--[\w-]+)\)/g, (_, token) =>
    theme.getPropertyValue(token).trim(),
  );
}
function pixels(value: string, root = 16) {
  const resolved = resolve(value);
  expect(resolved).toMatch(/^\d+(?:\.\d+)?rem$/);
  return Number.parseFloat(resolved) * root;
}
function luminance(hex: string) {
  return [1, 3, 5]
    .map((start) => Number.parseInt(hex.slice(start, start + 2), 16) / 255)
    .map((value) =>
      value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4,
    )
    .reduce(
      (total, value, index) => total + value * [0.2126, 0.7152, 0.0722][index],
      0,
    );
}
function contrast(foreground: string, background: string) {
  const [low, high] = [luminance(foreground), luminance(background)].sort(
    (a, b) => a - b,
  );
  return (high + 0.05) / (low + 0.05);
}

describe("workspace readability source contract", () => {
  it("uses a modular desktop reference-manager rem scale (15px body, 13px controls, 12px meta)", () => {
    for (const [size, selectors] of [
      [15, ["body", ".preserve-lines", ".question-block p", ".native-prose"]],
      [
        13,
        [
          ".button",
          "input",
          "textarea",
          "select",
          ".capability",
          ".notice",
          ".decision-box p",
          ".tool-intro",
        ],
      ],
      [12, [".field label", ".field small", ".form-note", ".protection", ".native-reason"]],
    ] as const) {
      for (const selector of selectors) {
        const sizes = values(selector, "font-size");
        expect(sizes.length, selector).toBeGreaterThan(0);
        expect(
          sizes.map((value) => pixels(value)),
          selector,
        ).toEqual(sizes.map(() => size));
      }
    }
    expect(values("body", "line-height")).toEqual(["var(--leading-body)"]);
    expect(Number(resolve("var(--leading-body)"))).toBeGreaterThanOrEqual(1.6);
    expect(Number(resolve("var(--leading-help)"))).toBeGreaterThanOrEqual(1.5);
  });
  it("has no sub-11px font-size overrides and uses scalable rem typography", () => {
    for (const rule of rules) {
      const value = rule.style.getPropertyValue("font-size").trim();
      if (!value || value === "inherit" || value.startsWith("clamp(")) continue;
      if (
        rule.selectors.every((selector) =>
          [".brand-symbol", ".file-icon"].includes(selector),
        )
      )
        continue;
      expect(pixels(value), rule.selectors.join(", ")).toBeGreaterThanOrEqual(
        11,
      );
      expect(pixels(value, 32)).toBe(pixels(value) * 2);
    }
    for (const selector of [".badge", ".nav-symbol", ".nav-number"]) {
      const desktopSizes = values(selector, "font-size", "");
      expect(
        desktopSizes.map((value) => pixels(value)),
        selector,
      ).toEqual(desktopSizes.map(() => 11));
    }
    for (const selector of [".record-id", "code", "pre", ".delivery-receipt .metadata"]) {
      const desktopSizes = values(selector, "font-size", "");
      expect(
        desktopSizes.map((value) => pixels(value)),
        selector,
      ).toEqual(desktopSizes.map(() => 12));
    }
  });
  it("uses compact desktop sidebar controls and two flexible mobile navigation columns", () => {
    expect(
      values(".sidebar nav", "grid-template-columns", "(max-width: 720px)"),
    ).toEqual(["repeat(2, minmax(0, 1fr))"]);
    for (const selector of [".sidebar nav a", ".project-control select"]) {
      const sizes = values(selector, "font-size");
      expect(sizes.map((value) => pixels(value)), selector).toEqual(
        sizes.map(() => 13),
      );
    }
    for (const selector of [".new-project", ".language-switch button"]) {
      const desktopSizes = values(selector, "font-size", "");
      expect(desktopSizes.map((value) => pixels(value)), selector).toEqual(
        desktopSizes.map(() => 12),
      );
    }
  });
  it("enforces compact desktop button/input geometry and mobile touch targets", () => {
    for (const selector of [
      ".button",
      ".project-control select",
      ".sidebar nav a",
      ".capability summary",
      "input",
      "select",
    ]) {
      const heights = values(selector, "min-height", "");
      expect(heights.length, selector).toBeGreaterThan(0);
      expect(
        heights.every((value) => Number.parseFloat(value) >= 30 && Number.parseFloat(value) <= 36),
        selector,
      ).toBe(true);
    }
    for (const selector of ["button", ".button", "input", "select", ".sidebar nav a"]) {
      const mobileHeights = values(selector, "min-height", "(max-width: 720px)");
      expect(mobileHeights.length, selector).toBeGreaterThan(0);
      expect(
        mobileHeights.every((value) => Number.parseFloat(value) >= 40),
        selector,
      ).toBe(true);
    }
    for (const selector of [
      "button",
      ".button",
      ".button.small",
      ".button.text-button",
      ".project-control select",
      ".sidebar .new-project",
      ".sidebar nav a",
      ".language-switch button",
      ".reading-desk-shell .project-control select",
      ".reading-desk-shell .sidebar nav > a",
      ".reading-desk-shell .reading-navigation-toggle",
      ".reading-desk-shell .language-switch button",
      ".integration-entry .button",
      ".catalog-toolbar input",
      ".catalog-toolbar select",
      ".catalog-organize .button",
      ".catalog-title",
      ".catalog-categories > button",
      ".catalog-view-switch button",
      ".catalog-category-card",
      ".catalog-master-sort",
      ".catalog-master-title",
      ".catalog-ext-link",
      ".overview-cat-row-btn",
      ".library-connection select",
      ".obsidian-validation input",
      ".integration-form-fields input",
      ".integration-form-fields select",
    ]) {
      const mobileHeights = combinedRules
        .filter(
          (rule) =>
            rule.selectors.includes(selector) &&
            rule.media === "(max-width: 760px)",
        )
        .map((rule) => rule.style.getPropertyValue("min-height").trim())
        .filter(Boolean);
      expect(mobileHeights.length, selector).toBeGreaterThan(0);
      expect(
        mobileHeights.every((value) => Number.parseFloat(value) >= 44),
        selector,
      ).toBe(true);
      const lastRule = combinedRules
        .filter(
          (rule) =>
            rule.selectors.includes(selector) &&
            Boolean(rule.style.getPropertyValue("min-height").trim()),
        )
        .at(-1);
      expect(lastRule?.media, selector).toBe("(max-width: 760px)");
    }
  });
  it("provides wrapping guards for long Chinese/English labels, paths and card headings", () => {
    for (const selector of [
      "h1",
      "h2",
      "h3",
      "p",
      ".field label",
      ".field small",
      ".button",
      ".sidebar nav a",
      ".file-path",
      ".protection > summary",
      "code",
      "select[multiple] option",
    ]) {
      expect(values(selector, "overflow-wrap"), selector).toContain("anywhere");
    }
    for (const selector of [
      ".brand",
      ".brand > span:last-child",
      ".page-heading > div",
      ".panel-heading > *",
    ]) {
      expect(
        values(selector, "min-width").map(Number.parseFloat),
        selector,
      ).toContain(0);
    }
    for (const selector of [".brand-symbol", ".nav-symbol"]) {
      expect(
        values(selector, "width").every((value) => value.endsWith("rem")),
        selector,
      ).toBe(true);
    }
    expect(values(".panel-button", "max-width")).toEqual(["calc(100% - 36px)"]);
    expect(values(".activity-row", "flex-wrap", "(max-width: 720px)")).toEqual([
      "wrap",
    ]);
  });
  it("pads readiness summaries without replacing native disclosure markers", () => {
    expect(values(".protection > summary", "padding")).toEqual(["0.35rem 0px"]);
    expect(values(".protection > summary", "display")).toEqual([]);
    expect(values(".protection > summary", "list-style")).toEqual([]);
  });
  it("keeps muted text and focus outlines distinct on the solid surfaces", () => {
    const token = (name: string) => theme.getPropertyValue(name).trim();
    for (const background of [
      token("--paper"),
      token("--white"),
      token("--wash"),
      "#e8efea",
    ]) {
      expect(contrast(token("--muted"), background)).toBeGreaterThanOrEqual(
        4.5,
      );
      expect(contrast(token("--focus"), background)).toBeGreaterThanOrEqual(3);
    }
    expect(contrast(token("--focus"), token("--navy"))).toBeGreaterThanOrEqual(
      3,
    );
  });
  it.each([
    [
      "研究問題與驗收條件".repeat(5),
      "請保留完整中文說明與證據限制，不可省略。".repeat(12),
    ],
    [
      "Instructions and acceptance criteria ".repeat(5).trim(),
      "Keep all evidence boundaries and limitations visible. "
        .repeat(12)
        .trim(),
    ],
  ])("preserves long field labels and accessible help: %s", (label, hint) => {
    render(
      <Field
        name="long-instructions"
        label={label}
        hint={hint}
        textarea
        required={false}
      />,
    );
    expect(
      screen.getByRole("textbox", { name: label }),
    ).toHaveAccessibleDescription(hint);
  });
});

it("keeps integration guidance in a compact independent bottom-left viewport-bounded popover", () => {
  expect(values(".integrations-panel", "position")).toContain("fixed");
  expect(values(".integrations-panel", "overflow-y")).toContain("auto");
  expect(values(".integration-entry .button", "width")).toContain("auto");
});

it("keeps the setup trigger secondary theme above normal-text contrast", () => {
  const foreground = values(".button.secondary", "color").at(-1)!;
  const background = values(".button.secondary", "background").at(-1)!;
  const hex = (value: string) => {
    const resolved = resolve(value);
    if (resolved.startsWith("#")) return resolved;
    const channels = resolved.match(/^rgb\((\d+),\s*(\d+),\s*(\d+)\)$/);
    expect(channels, "CSSOM must provide an opaque RGB color").not.toBeNull();
    return "#" + channels!.slice(1).map(channel => Number(channel).toString(16).padStart(2, "0")).join("");
  };
  expect(contrast(hex(foreground), hex(background))).toBeGreaterThanOrEqual(4.5);
});

it("avoids thick side-stripe callouts and generic theme overrides in library styling", () => {
  expect(libraryCss).not.toMatch(/:root\s*\{/);
  expect(libraryCss).not.toMatch(/--display-font\s*:/);
  expect(styles + "\n" + libraryCss).not.toMatch(/border-(?:left|right)\s*:\s*[2-9]px\s+solid/);
});

it("enforces design-engineering micro-interaction and scroll containment craft rules", () => {
  const combined = styles + "\n" + libraryCss;
  expect(combined).not.toMatch(/transition\s*:\s*all\b/i);
  expect(values(".integrations-panel", "overscroll-behavior")).toContain("contain");
  expect(values(".integrations-panel", "transform-origin")).toContain("bottom left");
  expect(
    libraryRules
      .filter((rule) => rule.selectors.includes(".catalog-list"))
      .map((rule) => rule.style.getPropertyValue("overscroll-behavior").trim()),
  ).toContain("contain");
  expect(values("button", "touch-action")).toContain("manipulation");
  expect(values("[data-tooltip]::after", "pointer-events")).toContain("none");
  for (const selector of [".icon-btn", ".sidebar .new-project", ".integration-entry .button"]) {
    expect(
      combinedRules
        .filter(
          (rule) =>
            rule.selectors.includes(selector) &&
            rule.media === "(max-width: 760px)",
        )
        .map((rule) => Number.parseFloat(rule.style.getPropertyValue("min-width")))
        .filter((value) => !Number.isNaN(value)),
      selector,
    ).toContain(44);
  }
});
