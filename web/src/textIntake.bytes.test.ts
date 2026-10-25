import { expect, it } from "vitest";
import {
  encodePaste,
  encodeTextBytes,
  readTextFile,
  validUnicode,
} from "./textIntake";

it("keeps BOM, CRLF, CR and non-BMP codepoints in the decoded preview and original encoded bytes", async () => {
  const raw = new TextEncoder().encode("\ufeffTitle\r\n😀 Abstract\rEnd");
  const encoded = await readTextFile(
    new File([raw], "public.md"),
    new AbortController().signal,
  );
  expect(encoded.text).toBe("\ufeffTitle\r\n😀 Abstract\rEnd");
  expect(encoded.format).toBe("md");
  expect(
    Array.from(atob(encoded.content_base64), (c) => c.charCodeAt(0)),
  ).toEqual(Array.from(raw));
});
it.each([
  new Uint8Array([0xff]),
  new Uint8Array([0xc0, 0xaf]),
  new Uint8Array([0xed, 0xa0, 0x80]),
  new Uint8Array([0xf0, 0x9f]),
])("rejects invalid UTF-8 rather than replacing bytes: %s", (raw) => {
  expect(() => encodeTextBytes(raw, "txt")).toThrow("strict UTF-8");
});
it("accepts exactly 40,000 bytes and rejects 40,001 without truncating", () => {
  expect(encodePaste("a".repeat(40000)).bytes).toBe(40000);
  expect(() => encodePaste("a".repeat(40001))).toThrow("40,000");
  expect(() => encodePaste("😀".repeat(10001))).toThrow("40,000");
});
it.each(["", " \r\n", "\ufeff \n", "text\0binary", "\ud800", "\udc00"])(
  "rejects empty, binary-looking and invalid scalar paste %j",
  (text) => {
    expect(() => encodePaste(text)).toThrow();
  },
);
it("preserves valid Unicode and treats pasted text as its own UTF-8 bytes", () => {
  expect(validUnicode("A😀\r\nB")).toBe(true);
  expect(encodePaste("A😀\r\nB").text).toBe("A😀\r\nB");
});
it("never reads unsupported or oversized files", async () => {
  await expect(
    readTextFile(new File(["a"], "paper.pdf"), new AbortController().signal),
  ).rejects.toThrow("not a PDF");
  await expect(
    readTextFile(
      new File([new Uint8Array(40001)], "public.txt"),
      new AbortController().signal,
    ),
  ).rejects.toThrow("40,000");
});
it("honors cancellation before reading file bytes", async () => {
  const c = new AbortController();
  c.abort();
  await expect(
    readTextFile(new File(["a"], "public.txt"), c.signal),
  ).rejects.toMatchObject({ name: "AbortError" });
});
