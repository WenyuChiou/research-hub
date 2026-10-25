import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Field } from "./components";
import tokens from "./tokens.css?raw";
import styles from "./styles.css?raw";

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
  it("keeps body at 18px and meaningful helper/control text at 16px by default", () => {
    for (const [size, selectors] of [
      [18, ["body", ".preserve-lines", ".question-block p"]],
      [
        16,
        [
          ".button",
          "input",
          "textarea",
          "select",
          ".field label",
          ".field small",
          ".form-note",
          ".protection",
          ".capability",
          ".notice",
          ".decision-box p",
          ".tool-intro",
        ],
      ],
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
    expect(Number(resolve("var(--leading-help)"))).toBeGreaterThanOrEqual(1.6);
  });
  it("has no sub-14px font-size overrides and uses scalable rem typography", () => {
    for (const rule of rules) {
      const value = rule.style.getPropertyValue("font-size").trim();
      if (!value || value === "inherit" || value.startsWith("clamp(")) continue;
      if (
        rule.selectors.every((selector) =>
          [
            ".brand-symbol",
            ".folio span",
            ".folio strong",
            ".file-icon",
          ].includes(selector),
        )
      )
        continue;
      expect(pixels(value), rule.selectors.join(", ")).toBeGreaterThanOrEqual(
        14,
      );
      expect(pixels(value, 32)).toBe(pixels(value) * 2);
    }
    // Decorative aria-hidden folio typography is the only tiny font shorthand.
    for (const selector of [
      ".badge",
      ".record-id",
      "code",
      "pre",
      ".content-footer",
      ".delivery-receipt .metadata",
    ]) {
      expect(
        values(selector, "font-size").map((value) => pixels(value)),
        selector,
      ).toEqual(values(selector, "font-size").map(() => 14));
    }
  });
  it("uses two flexible mobile navigation columns without shrinking labels", () => {
    expect(
      values(".sidebar nav", "grid-template-columns", "(max-width: 720px)"),
    ).toEqual(["repeat(2, minmax(0, 1fr))"]);
    for (const selector of [
      ".sidebar nav a",
      ".project-control select",
      ".new-project",
      ".language-switch button",
    ]) {
      const sizes = values(selector, "font-size");
      expect(
        sizes.map((value) => pixels(value)),
        selector,
      ).toEqual(sizes.map(() => 16));
    }
  });
  it("sets 44px minimum heights on the specific controls as well as generic controls", () => {
    for (const selector of [
      ".button",
      ".button.text-button",
      ".notice button",
      ".capability summary",
      ".inspect summary",
      ".protection > summary",
      ".project-control select",
      ".new-project",
      ".language-switch button",
      "input",
      "select",
    ]) {
      const heights = values(selector, "min-height");
      expect(heights.length, selector).toBeGreaterThan(0);
      expect(
        heights.every((value) => Number.parseFloat(value) >= 44),
        selector,
      ).toBe(true);
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
    expect(values(".panel-button", "max-width")).toEqual(["calc(100% - 44px)"]);
    expect(values(".activity-row", "flex-wrap", "(max-width: 720px)")).toEqual([
      "wrap",
    ]);
  });
  it("pads readiness summaries without replacing native disclosure markers", () => {
    expect(values(".protection > summary", "padding")).toEqual(["0.5rem 0px"]);
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
    expect(values(".content-footer", "color")).toEqual(["var(--muted)"]);
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

it("keeps integration guidance in an independent viewport-bounded panel", () => {
  expect(values(".integrations-panel", "position")).toContain("fixed");
  expect(values(".integrations-panel", "overflow-y")).toContain("auto");
  expect(values(".integration-entry", "flex-basis")).toContain("100%");
});
