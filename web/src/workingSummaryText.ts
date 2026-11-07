// Match working_summary._text: Python str.strip() includes U+0085 and the
// U+001C–U+001F separators, but not U+FEFF. JavaScript trim() differs on both.
const edgeWhitespace = /^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/g;

/** Normalize submitted prose only; preserve the user's raw textarea draft. */
export function normalizeWorkingSummaryText(value: string): string {
  return value.replace(/\r\n/g, "\n").replace(edgeWhitespace, "");
}
