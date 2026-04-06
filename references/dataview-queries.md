---
title: Dataview Query Examples
description: Ready-to-use Dataview queries for paper filtering, status tracking, and thesis integration
---

# Dataview Query Examples

## Dataview Integration for Obsidian

The YAML frontmatter fields support powerful Dataview queries in Obsidian. Install the Dataview community plugin to use these.

**Example Dataview queries:**

**All unread papers in a category:**
```dataview
TABLE title, authors, year, sub-category
FROM "raw"
WHERE status = "unread" AND method-type = "traditional-abm"
SORT year DESC
```

**Papers sorted by citation count:**
```dataview
TABLE title, authors, year, citation-count
FROM "raw"
WHERE citation-count > 0
SORT citation-count DESC
LIMIT 20
```

**Papers grouped by thesis chapter:**
```dataview
TABLE title, authors, year, status
FROM "raw"
WHERE thesis-chapter != ""
GROUP BY thesis-chapter
SORT thesis-chapter ASC
```

**Reading pipeline (papers by status):**
```dataview
TABLE title, authors, year, sub-category
FROM "raw"
GROUP BY status
SORT choice(status, "unread", 1, "skimming", 2, "deep-read", 3, "cited", 4) ASC
```

**Recently added papers (last 30 days):**
```dataview
TABLE title, authors, year, sub-category, status
FROM "raw"
SORT file.ctime DESC
LIMIT 15
```

**Papers addressing specific research questions:**
```dataview
TABLE title, authors, year, status
FROM "raw"
WHERE contains(research-questions, "RQ1")
SORT year DESC
```

**Papers with related papers populated:**
```dataview
TABLE title, length(related-papers) AS "# Related"
FROM "raw"
WHERE length(related-papers) > 0
SORT length(related-papers) DESC
```

> **Tip**: Hub sub-category pages can use Dataview queries instead of manually maintained link lists. Replace the static paper list with a Dataview TABLE query filtered by `sub-category`.
