// brief_to_docx.js — convert a research-design-helper design_brief (.md) to a styled Word document (.docx)
//
// Sister script to skills/gap-to-topic/scripts/dossier_to_docx.js — same
// Markdown → Word converter, default stem "design_brief" (Stage 3a artifact)
// instead of "topic_dossier" (Stage 2 artifact). The verdict-colour regex
// is kept verbatim from the dossier generator; it simply doesn't fire on
// design_brief content (no "Do not pursue" / "Not assessed" strings),
// which is the correct no-op behaviour.
//
// Prerequisite: npm install -g docx   (or: cd scripts && npm install docx  for local)
//
// Usage:
//   node brief_to_docx.js [stem-or-path] [--no-toc]
//
//   stem-or-path  Stem name ("design_brief") relative to cwd, OR an absolute path
//                 (with or without .md/.docx extension — the script adds them).
//                 Default: "design_brief"
//   --no-toc      Skip the Table of Contents field (avoid empty Word TOC on short docs).
//
// Examples:
//   node brief_to_docx.js design_brief --no-toc
//   node brief_to_docx.js /abs/path/to/en/design_brief
//   node brief_to_docx.js design_brief.zh-TW   (triggers JhengHei font)
//
// Font auto-selection:
//   filename matches /.zh|zh-|zh_|-tw|-cn/i  -> Microsoft JhengHei
//   otherwise                                 -> Arial
//
// Verdict colour coding inherited from dossier_to_docx.js (cells in
// scorecards / verdict cards — does NOT fire on design_brief content):
//   "Do not pursue" / "不予推進"              -> light red   (#F4DEDE)
//   "Worth pursuing … only if" / conditional  -> light yellow (#FFF4D6)
//   "Worth pursuing" (unconditional)          -> light green  (#E2F0DA)
//   "Not assessed" / "未評估"                 -> light grey   (#EEEEEE)
//   All other cells                           -> white

const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, LevelFormat, TableOfContents, HeadingLevel, BorderStyle,
  WidthType, ShadingType, PageBreak,
} = require("docx");

// ---- argument parsing ----
const NOTOC = process.argv.includes("--no-toc");
const ARG = process.argv.slice(2).find((a) => !a.startsWith("--")) || "design_brief";

// Strip .md or .docx extension if provided so we work from the bare stem
const stem = ARG.replace(/\.(md|docx)$/i, "");

// Font: detect Chinese filename pattern
const FONT = /\.zh|zh-|zh_|-tw|-cn/i.test(stem) ? "Microsoft JhengHei" : "Arial";

// Resolve source (.md) and output (.docx) paths.
// If the stem is absolute (contains a path separator), write alongside it.
// Otherwise resolve relative to process.cwd() so the script works from any directory.
const isAbs = path.isAbsolute(stem) || stem.includes("/") || stem.includes("\\");
const SRC = isAbs ? path.resolve(stem + ".md") : path.resolve(process.cwd(), stem + ".md");
const OUT = isAbs ? path.resolve(stem + ".docx") : path.resolve(process.cwd(), stem + ".docx");

const CONTENT_W = 9360;

// ---- inline markdown -> TextRun[] ----
function parseInline(text, base = {}) {
  const runs = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) runs.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const t = m[0];
    if (t.startsWith("**")) runs.push(new TextRun({ text: t.slice(2, -2), bold: true, ...base }));
    else if (t.startsWith("`")) runs.push(new TextRun({ text: t.slice(1, -1), font: "Consolas", size: 19, ...base }));
    else runs.push(new TextRun({ text: t.slice(1, -1), italics: true, ...base }));
    last = re.lastIndex;
  }
  if (last < text.length) runs.push(new TextRun({ text: text.slice(last), ...base }));
  if (!runs.length) runs.push(new TextRun({ text: "", ...base }));
  return runs;
}

// ---- block parser ----
if (!fs.existsSync(SRC)) {
  console.error("ERROR: source file not found:", SRC);
  process.exit(1);
}
const lines = fs.readFileSync(SRC, "utf8").replace(/\r\n/g, "\n").split("\n");
const blocks = [];
let i = 0;
function lastBlock() { return blocks[blocks.length - 1]; }
while (i < lines.length) {
  const ln = lines[i];
  const t = ln.trim();
  if (/^#{1,3}\s/.test(t)) {
    const level = t.match(/^#+/)[0].length;
    blocks.push({ type: "h", level, text: t.replace(/^#+\s/, "") });
    i++; continue;
  }
  if (t === "---") { blocks.push({ type: "hr" }); i++; continue; }
  if (t === "") { blocks.push({ type: "blank" }); i++; continue; }
  if (t.startsWith(">")) {
    const buf = [];
    while (i < lines.length && lines[i].trim().startsWith(">")) {
      buf.push(lines[i].trim().replace(/^>\s?/, "")); i++;
    }
    blocks.push({ type: "note", text: buf.join(" ").replace(/\s+/g, " ").trim() });
    continue;
  }
  if (t.startsWith("|")) {
    const rows = [];
    while (i < lines.length && lines[i].trim().startsWith("|")) {
      const cells = lines[i].trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(c => c.trim());
      // Skip Markdown table separator row (|---|---|, |:---|---:|, …) —
      // it is alignment metadata, not a data row; the previous parser
      // pushed it and Word rendered a literal "---" row.
      const isSep = cells.length > 0 && cells.every(c => /^:?-+:?$/.test(c));
      if (!isSep) rows.push(cells);
      i++;
    }
    blocks.push({ type: "table", rows });
    continue;
  }
  if (t.startsWith("- ")) {
    let txt = t.slice(2);
    i++;
    while (i < lines.length && /^\s{2,}\S/.test(lines[i])) { txt += " " + lines[i].trim(); i++; }
    const lb = lastBlock();
    if (lb && lb.type === "list") lb.items.push(txt);
    else blocks.push({ type: "list", items: [txt] });
    continue;
  }
  // normal paragraph (join wrapped lines until blank / marker)
  let txt = t;
  i++;
  while (i < lines.length) {
    const nx = lines[i], nt = nx.trim();
    if (nt === "" || nt === "---" || /^#{1,3}\s/.test(nt) || nt.startsWith("|") || nt.startsWith(">") || nt.startsWith("- ")) break;
    txt += " " + nt; i++;
  }
  blocks.push({ type: "p", text: txt });
}

// ---- render ----
const border = { style: BorderStyle.SINGLE, size: 1, color: "BFBFBF" };
const borders = { top: border, bottom: border, left: border, right: border,
  insideHorizontal: border, insideVertical: border };
const colWidths = (n) => {
  if (n === 2) return [2400, 6960];
  if (n === 4) return [1000, 2790, 3570, 2000];
  if (n === 5) return [560, 3960, 560, 1480, 2800];
  const w = Math.floor(CONTENT_W / n); return Array(n).fill(w);
};

// Cell-shading colour by row (header = dark blue) and, for non-header
// cells, by verdict-keyword detection. Patterns are checked in order:
// conditional "only if" must win over the plain green case.
function cellFill(r, cell) {
  if (r === 0) return "1F3B5B"; // header dark blue
  const lc = cell.toLowerCase();
  // English verdict keywords
  if (/do not pursue/.test(lc)) return "F4DEDE";          // light red
  if (/worth pursuing/.test(lc) && /only if/.test(lc)) return "FFF4D6"; // light yellow
  if (/worth pursuing/.test(lc)) return "E2F0DA";         // light green
  if (/not assessed/.test(lc)) return "EEEEEE";           // light grey
  // zh-TW verdict keywords (toLowerCase is a no-op on CJK so cell is raw)
  if (/不予推進/.test(cell)) return "F4DEDE";              // light red
  if (/值得推進/.test(cell) && /只|須|待決|條件/.test(cell)) return "FFF4D6"; // light yellow
  if (/值得推進/.test(cell)) return "E2F0DA";              // light green
  if (/未評估/.test(cell)) return "EEEEEE";                // light grey
  return "FFFFFF";                                         // default white
}

function mkTable(rows) {
  const n = rows[0].length;
  const cw = colWidths(n);
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: cw,
    rows: rows.map((cells, r) => new TableRow({
      tableHeader: r === 0,
      children: cells.map((cell, c) => new TableCell({
        borders,
        width: { size: cw[c], type: WidthType.DXA },
        shading: { fill: cellFill(r, cell), type: ShadingType.CLEAR },
        margins: { top: 70, bottom: 70, left: 110, right: 110 },
        children: [new Paragraph({
          spacing: { before: 20, after: 20 },
          children: parseInline(cell, r === 0 ? { bold: true, color: "FFFFFF", size: 19 } : { size: 19 }),
        })],
      })),
    })),
  });
}

const children = [];
let tocInserted = false;
for (const b of blocks) {
  if (b.type === "blank" || b.type === "hr") continue;
  if (b.type === "h") {
    const hl = b.level === 1 ? HeadingLevel.HEADING_1 : b.level === 2 ? HeadingLevel.HEADING_2 : HeadingLevel.HEADING_3;
    children.push(new Paragraph({ heading: hl, children: parseInline(b.text) }));
  } else if (b.type === "note") {
    children.push(new Paragraph({
      spacing: { before: 60, after: 120 },
      indent: { left: 360 },
      border: { left: { style: BorderStyle.SINGLE, size: 12, color: "B0B0B0", space: 12 } },
      children: parseInline(b.text, { italics: true, color: "5A5A5A", size: 19 }),
    }));
  } else if (b.type === "p") {
    children.push(new Paragraph({ spacing: { before: 80, after: 80 }, children: parseInline(b.text) }));
  } else if (b.type === "list") {
    for (const it of b.items) {
      children.push(new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        spacing: { before: 40, after: 40 },
        children: parseInline(it),
      }));
    }
  } else if (b.type === "table") {
    children.push(new Paragraph({ spacing: { before: 80, after: 80 }, children: [] }));
    children.push(mkTable(b.rows));
    children.push(new Paragraph({ spacing: { after: 80 }, children: [] }));
    if (!tocInserted && !NOTOC) {
      tocInserted = true;
      children.push(new Paragraph({ pageBreakBefore: true, heading: HeadingLevel.HEADING_2,
        children: [new TextRun("Contents")] }));
      children.push(new TableOfContents("Table of Contents", { hyperlink: true, headingStyleRange: "1-3" }));
      children.push(new Paragraph({ children: [new PageBreak()] }));
    }
  }
}

const doc = new Document({
  styles: {
    default: { document: { run: { font: FONT, size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 34, bold: true, font: FONT, color: "1F3B5B" },
        paragraph: { spacing: { before: 240, after: 200 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 27, bold: true, font: FONT, color: "1F3B5B" },
        paragraph: { spacing: { before: 260, after: 120 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 23, bold: true, font: FONT, color: "2E2E2E" },
        paragraph: { spacing: { before: 160, after: 60 }, outlineLevel: 2 } },
    ],
  },
  numbering: {
    config: [
      { reference: "bullets",
        levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 420, hanging: 280 } } } }] },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    children,
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(OUT, buf);
  console.log("WROTE", OUT, buf.length, "bytes");
}).catch(err => {
  console.error("ERROR generating docx:", err.message);
  process.exit(1);
});
