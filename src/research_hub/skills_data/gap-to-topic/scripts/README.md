# scripts/dossier_to_docx.js

Convert a `gap-to-topic` dossier Markdown file into a styled Word document
(.docx) using `docx` 9.x.

## What it produces

A `.docx` file alongside the source `.md` with:

- Heading styles (H1 navy, H2 navy, H3 dark grey) using the auto-selected font
- Bullet lists via a numbering reference (not a unicode glyph)
- Tables with dual-width DXA column sizing
- Verdict colour coding on scorecard and verdict-card cells:
  - "Do not pursue" / "不予推進" — light red `#F4DEDE`
  - "Worth pursuing … only if" / conditional — light yellow `#FFF4D6`
  - "Worth pursuing" (unconditional) — light green `#E2F0DA`
  - "Not assessed" / "未評估" — light grey `#EEEEEE`
- Table separator rows (`|---|---|`) skipped — they do not appear as "---" cells in Word
- Optional Table of Contents + page break inserted after the first table
  (omit with `--no-toc` for short docs where Word's empty TOC field is distracting)

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

Run from the directory that contains your `topic_dossier.md` (the dossier
output directory — typically `.research/` or `en/` / `zh-TW/`):

```bash
# English dossier (Arial font, with TOC):
node /path/to/skills/gap-to-topic/scripts/dossier_to_docx.js topic_dossier

# English dossier, skip TOC:
node /path/to/skills/gap-to-topic/scripts/dossier_to_docx.js topic_dossier --no-toc

# zh-TW dossier (JhengHei font):
node /path/to/skills/gap-to-topic/scripts/dossier_to_docx.js topic_dossier.zh-TW --no-toc

# Absolute path (writes .docx alongside the .md):
node dossier_to_docx.js /abs/path/to/en/topic_dossier
```

The output `.docx` is written to the same directory as the `.md` file.

## Integration in the gap-to-topic workflow

After `gap-to-topic` writes `.research/topic_dossier.md`, run this script from
that directory to produce the matching `.docx` deliverable. See SKILL.md §4.5
for the contracted post-processing step.
