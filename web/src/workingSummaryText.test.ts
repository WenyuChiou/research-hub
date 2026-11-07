import { describe, expect, it } from "vitest";
import { normalizeWorkingSummaryText } from "./workingSummaryText";

const pythonWhitespace = [9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760,
  8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288];

describe("working-summary server normalization", () => {
  it.each(pythonWhitespace)("strips Python whitespace U+%s only at edges", codepoint => {
    const space = String.fromCodePoint(codepoint);
    expect(normalizeWorkingSummaryText(space + "A" + space + "B" + space)).toBe("A" + space + "B");
    expect(normalizeWorkingSummaryText(space)).toBe("");
  });
  it.each([0, 0x200b, 0x2060, 0xfeff, 0x1f33f])("preserves non-Python-whitespace U+%s", codepoint => {
    const character = String.fromCodePoint(codepoint);
    expect(normalizeWorkingSummaryText(character + "prose" + character)).toBe(character + "prose" + character);
  });
  it("normalizes CRLF without changing internal line breaks, lone CR or Unicode prose", () => {
    expect(normalizeWorkingSummaryText("\u0085摘要\r\n🌿\r下一行\u0085")).toBe("摘要\n🌿\r下一行");
  });
  it("is idempotent without state leaking from the shared regular expression", () => {
    for (const raw of ["\u0085prose\u0085", "\ufeffprose\ufeff", "\u001c", " text\r\n "]) {
      const once = normalizeWorkingSummaryText(raw);
      expect(normalizeWorkingSummaryText(once)).toBe(once);
      expect(normalizeWorkingSummaryText(raw)).toBe(once);
    }
  });
});
