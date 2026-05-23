# scripts/brief_to_docx.js

Convert a `research-design-helper` design brief Markdown file into a styled
Word document (.docx) using `docx` 9.x.

This is the **sister script** to
`skills/gap-to-topic/scripts/dossier_to_docx.js` — same Markdown → Word
converter, but the default stem is `design_brief` (the Stage 3a artifact)
instead of `topic_dossier` (the Stage 2 artifact). The two scripts share
the same internal logic so a single fix lands in both via parallel PRs.

## What it produces

A `.docx` file alongside the source `.md` with:

- Heading styles (H1 navy, H2 navy, H3 dark grey) using the auto-selected font
- Bullet lists via a numbering reference (not a unicode glyph)
- Tables with dual-width DXA column sizing (the design brief §5 risk
  register renders cleanly as a 4-column table)
- Table separator rows (`|---|---|`) skipped — they do not appear as
  "---" cells in Word
- Optional Table of Contents + page break inserted after the first table
  (omit with `--no-toc` for short docs where Word's empty TOC field is
  distracting — recommended for `design_brief.md` which has only 5
  sections)

The verdict-colour coding regex (light red / yellow / green / grey
on scorecard / verdict cells) is inherited from `dossier_to_docx.js`
verbatim. It does NOT fire on `design_brief.md` content (no "Do not
pursue" / "Not assessed" / "不予推進" / "未評估" strings appear in a
design brief), which is the correct no-op behaviour. Leaving the
regex in keeps the two scripts byte-near-identical so future maintenance
patches land in parallel.

Font auto-selection: if the filename contains `.zh`, `zh-`, `zh_`, `-tw`, or
`-cn` (case-insensitive), the document body uses **Microsoft JhengHei**;
otherwise **Arial**.

## Prerequisite

Install the `docx` npm package before running the script:

```
# Global install (available everywhere):
npm install -g docx

# Local install (available only from the scripts/ directory):
cd scripts && npm install docx
```

If `docx` is not installed, Node.js will throw a `Cannot find module 'docx'`
error when the script is run. Install it and re-run.

## Invocation

Run from the directory that contains your `design_brief.md` (typically
`.research/`):

```bash
# English brief (Arial font, no TOC recommended for short docs):
node /path/to/skills/research-design-helper/scripts/brief_to_docx.js design_brief --no-toc

# zh-TW brief (JhengHei font auto-selected by filename):
node /path/to/skills/research-design-helper/scripts/brief_to_docx.js design_brief.zh-TW --no-toc

# Absolute path (writes .docx alongside the .md):
node brief_to_docx.js /abs/path/to/.research/design_brief
```

The output `.docx` is written to the same directory as the `.md` file.

## Integration in the research-design-helper workflow

`design_brief.md` is the canonical Stage 3a artifact and remains the
primary deliverable. The `.docx` is an **optional convenience** for
sharing with advisors / committee members who prefer Word over Markdown
— it is NOT part of the contracted output and is not consumed by
downstream skills (Stage 3b reads the `.md` frontmatter + section 1
directly).

See SKILL.md `## Generate .docx (optional)` for the post-processing
step.
