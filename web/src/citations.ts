import { safeSourceUrl } from "./api";
import type { ResearchRecord } from "./types";

const text = (value: unknown) =>
  typeof value === "string" || typeof value === "number" ? String(value) : "";

function strings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function cleanLine(value: string): string {
  return value.replace(/[\r\n\u0085\u2028\u2029]+/g, " ").trim();
}

export interface StructuredAuthor {
  family: string;
  given: string;
  literal?: string;
}

export function parseStructuredAuthors(value: unknown): StructuredAuthor[] {
  const rawList =
    typeof value === "string"
      ? value.trim()
        ? [value.trim()]
        : []
      : Array.isArray(value)
        ? value
        : [];
  const out: StructuredAuthor[] = [];
  for (const item of rawList) {
    if (typeof item === "string") {
      const cleaned = cleanLine(item);
      if (!cleaned) continue;
      if (cleaned.includes(",")) {
        const [family, ...rest] = cleaned.split(",");
        out.push({
          family: family.trim(),
          given: rest.join(",").trim(),
        });
      } else {
        const parts = cleaned.split(/\s+/).filter(Boolean);
        if (parts.length === 1) {
          out.push({ family: parts[0], given: "" });
        } else {
          out.push({
            family: parts[parts.length - 1],
            given: parts.slice(0, -1).join(" "),
          });
        }
      }
    } else if (item && typeof item === "object") {
      const obj = item as Record<string, unknown>;
      const family = cleanLine(text(obj.family));
      const given = cleanLine(text(obj.given));
      const direct = cleanLine(text(obj.name));
      if (family) {
        out.push({ family, given });
      } else if (direct) {
        const parts = direct.split(/\s+/).filter(Boolean);
        out.push(
          parts.length > 1
            ? { family: parts[parts.length - 1], given: parts.slice(0, -1).join(" ") }
            : { family: direct, given: "" },
        );
      }
    }
  }
  return out;
}

function dedupeKeywords(record: ResearchRecord): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  const cat = cleanLine(text(record.data.category) || text(record.data.sub_category));
  for (const raw of [cat, ...strings(record.data.tags), ...strings(record.data.labels)]) {
    const cleaned = cleanLine(raw).replace(/^#+/, "").trim();
    if (!cleaned) continue;
    const key = cleaned.toLocaleLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      out.push(cleaned);
    }
  }
  return out;
}

function recordSummary(record: ResearchRecord): string {
  return (
    [record.data.summary, record.data.abstract].find(
      (v): v is string => typeof v === "string" && Boolean(v.trim()),
    ) || ""
  );
}

function recordScope(record: ResearchRecord): string {
  return (
    cleanLine(text(record.data.reading_level)) ||
    cleanLine(text(record.data.reading_scope)) ||
    "unknown"
  );
}

export function makeCiteKey(record: ResearchRecord, index = 0): string {
  const authors = parseStructuredAuthors(record.data.authors);
  const surname =
    (authors[0]?.family || "source").toLowerCase().replace(/[^a-z0-9]/g, "") ||
    "source";
  const year = text(record.data.year).replace(/[^0-9]/g, "").slice(0, 4) || "nd";
  const titleWord =
    text(record.data.title)
      .toLowerCase()
      .split(/[^a-z0-9]+/)
      .find(
        (w) =>
          w.length >= 4 &&
          !["with", "from", "that", "this", "into", "over"].includes(w),
      ) || `item${index + 1}`;
  return `${surname}${year}${titleWord}`;
}

export function formatInTextCitation(record: ResearchRecord): string {
  const authors = parseStructuredAuthors(record.data.authors);
  const year = cleanLine(text(record.data.year)) || "n.d.";
  if (!authors.length) {
    const shortTitle = cleanLine(text(record.data.title)).slice(0, 32) || "Source";
    return `(${shortTitle}, ${year})`;
  }
  if (authors.length === 1) return `(${authors[0].family}, ${year})`;
  if (authors.length === 2) return `(${authors[0].family} & ${authors[1].family}, ${year})`;
  return `(${authors[0].family} et al., ${year})`;
}

export function formatPandocCite(record: ResearchRecord, index = 0): string {
  return `[@${makeCiteKey(record, index)}]`;
}

export function formatLatexCite(record: ResearchRecord, index = 0): string {
  return `\\cite{${makeCiteKey(record, index)}}`;
}

function formatApaAuthor(author: StructuredAuthor): string {
  if (!author.given) return author.family;
  const initials = author.given
    .split(/[\s.-]+/)
    .filter(Boolean)
    .map((part) => `${part[0].toUpperCase()}.`)
    .join(" ");
  return `${author.family}, ${initials}`;
}

/** Formats a single reference in clean APA 7th style for Word / Docs / Markdown. */
export function formatApaReference(record: ResearchRecord): string {
  const authors = parseStructuredAuthors(record.data.authors);
  let authorPart = "";
  if (authors.length === 1) {
    authorPart = formatApaAuthor(authors[0]);
  } else if (authors.length === 2) {
    authorPart = `${formatApaAuthor(authors[0])}, & ${formatApaAuthor(authors[1])}`;
  } else if (authors.length > 2) {
    const shown = authors.slice(0, 19).map(formatApaAuthor);
    authorPart =
      authors.length <= 20
        ? `${shown.slice(0, -1).join(", ")}, & ${formatApaAuthor(authors[authors.length - 1])}`
        : `${shown.join(", ")}, ... ${formatApaAuthor(authors[authors.length - 1])}`;
  }
  const year = cleanLine(text(record.data.year)) || "n.d.";
  const title = cleanLine(text(record.data.title)) || "Untitled source";
  const venue = cleanLine(text(record.data.venue) || text(record.data.journal));
  const doi = cleanLine(text(record.data.doi)).replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, "");
  const safeUrl =
    record.data.locator_kind !== "local-copy"
      ? safeSourceUrl(record.data.locator) || ""
      : "";
  const linkPart = doi ? `https://doi.org/${doi}` : safeUrl;

  return [
    authorPart ? `${authorPart} (${year}).` : `${title}. (${year}).`,
    authorPart ? `${title.replace(/\.+$/, "")}.` : "",
    venue ? `${venue.replace(/\.+$/, "")}.` : "",
    linkPart,
  ]
    .filter(Boolean)
    .join(" ");
}

export function buildApaBibliography(records: ResearchRecord[]): string {
  return (
    [...records]
      .map(formatApaReference)
      .sort((a, b) => a.localeCompare(b))
      .join("\n\n") + "\n"
  );
}

/** Builds universal RIS (.ris) export for EndNote, Zotero, Mendeley, RefWorks, and Covidence. */
export function buildRisExport(records: ResearchRecord[]): string {
  return (
    records
      .map((record) => {
        const authors = parseStructuredAuthors(record.data.authors);
        const title = cleanLine(text(record.data.title));
        const year = cleanLine(text(record.data.year)).replace(/[^0-9]/g, "").slice(0, 4);
        const venue = cleanLine(text(record.data.venue) || text(record.data.journal));
        const doi = cleanLine(text(record.data.doi)).replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, "");
        const url =
          record.data.locator_kind !== "local-copy"
            ? safeSourceUrl(record.data.locator) || ""
            : "";
        const keywords = dedupeKeywords(record);
        const summary = cleanLine(recordSummary(record));
        const scope = recordScope(record);
        const identity = cleanLine(text(record.data.identity_status)) || "unverified";

        const lines: string[] = ["TY  - JOUR"];
        if (title) lines.push(`TI  - ${title}`);
        for (const a of authors) {
          lines.push(`AU  - ${a.given ? `${a.family}, ${a.given}` : a.family}`);
        }
        if (year) lines.push(`PY  - ${year}`);
        if (venue) lines.push(`JO  - ${venue}`);
        if (doi) lines.push(`DO  - ${doi}`);
        if (url) lines.push(`UR  - ${url}`);
        for (const kw of keywords) {
          lines.push(`KW  - ${kw}`);
        }
        if (summary) lines.push(`AB  - ${summary}`);
        lines.push(`N1  - Reading scope: ${scope}; Identity: ${identity}`);
        lines.push("ER  - ");
        return lines.join("\r\n");
      })
      .join("\r\n\r\n") + "\r\n"
  );
}

/** Builds CSL-JSON (.json) for Pandoc, Quarto, Typst, Zotero, and Obsidian Citations plugin. */
export function buildCslJsonExport(records: ResearchRecord[]): string {
  const usedIds = new Set<string>();
  const items = records.map((record, index) => {
    let id = makeCiteKey(record, index);
    if (usedIds.has(id)) id = `${id}_${index + 1}`;
    usedIds.add(id);

    const authors = parseStructuredAuthors(record.data.authors);
    const yearNum = Number.parseInt(cleanLine(text(record.data.year)), 10);
    const venue = cleanLine(text(record.data.venue) || text(record.data.journal));
    const doi = cleanLine(text(record.data.doi)).replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, "");
    const url =
      record.data.locator_kind !== "local-copy"
        ? safeSourceUrl(record.data.locator) || ""
        : "";
    const keywords = dedupeKeywords(record);
    const summary = cleanLine(recordSummary(record));
    const scope = recordScope(record);
    const identity = cleanLine(text(record.data.identity_status)) || "unverified";

    const entry: Record<string, unknown> = {
      id,
      type: "article-journal",
      title: cleanLine(text(record.data.title)),
    };
    if (authors.length) {
      entry.author = authors.map((a) =>
        a.given ? { family: a.family, given: a.given } : { family: a.family },
      );
    }
    if (Number.isFinite(yearNum) && yearNum >= 1000 && yearNum <= 2100) {
      entry.issued = { "date-parts": [[yearNum]] };
    }
    if (venue) entry["container-title"] = venue;
    if (doi) entry.DOI = doi;
    if (url) entry.URL = url;
    if (keywords.length) entry.keyword = keywords.join(", ");
    if (summary) entry.abstract = summary;
    entry.note = `Reading scope: ${scope}; Identity: ${identity}`;
    return entry;
  });
  return JSON.stringify(items, null, 2) + "\n";
}

/**
 * Generates an Obsidian Bases (.base) YAML database file compatible with
 * Obsidian v1.9+ / v1.12+ and kepano/obsidian-skills.
 */
export function buildObsidianBaseYaml(
  clusterSlug?: string,
  projectTitle?: string,
): string {
  const safeSlug = (clusterSlug || "research-hub")
    .replace(/[^a-z0-9-_]/gi, "-")
    .toLowerCase();
  const safeTitle = cleanLine(projectTitle || safeSlug).replace(/"/g, '\\"');
  return [
    `# Obsidian Base for ${safeTitle} (compatible with Obsidian v1.9+ / v1.12+ & obsidian-skills)`,
    "filters:",
    "  and:",
    '    - \'file.ext == "md"\'',
    '    - \'reading_scope != null\'',
    "views:",
    "  - type: table",
    '    name: "All Literature"',
    "    order:",
    "      - file.name",
    "      - title",
    "      - year",
    "      - category",
    "      - reading_scope",
    "      - screening",
    "      - tags",
    "      - doi",
    "    groupBy:",
    "      property: category",
    "      direction: ASC",
    "  - type: table",
    '    name: "Included Cohort"',
    "    filters:",
    "      and:",
    '        - \'screening == "include"\'',
    "    order:",
    "      - year",
    "      - title",
    "      - category",
    "      - reading_scope",
    "      - doi",
    "    groupBy:",
    "      property: year",
    "      direction: DESC",
    "  - type: cards",
    '    name: "Needs Full-Text or Triage"',
    "    filters:",
    "      or:",
    '        - \'screening == "unscreened"\'',
    '        - \'reading_scope != "full-text"\'',
    "    order:",
    "      - title",
    "      - reading_scope",
    "      - screening",
    "      - category",
    "",
  ].join("\n");
}

export function extractVaultName(vaultPath?: string | null): string {
  if (!vaultPath || typeof vaultPath !== "string") return "";
  const trimmed = vaultPath.trim().replace(/[\\/]+$/, "");
  if (!trimmed) return "";
  const parts = trimmed.split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] || "";
}

export function buildObsidianUri(
  vaultName?: string | null,
  filePath?: string | null,
): string | null {
  const cleanVault = cleanLine(vaultName || "");
  if (!cleanVault) return null;
  const params = [`vault=${encodeURIComponent(cleanVault)}`];
  const cleanFile = cleanLine(filePath || "").replace(/^[\\/]+/, "");
  if (cleanFile && !cleanFile.includes("..")) {
    params.push(`file=${encodeURIComponent(cleanFile)}`);
  }
  return `obsidian://open?${params.join("&")}`;
}
