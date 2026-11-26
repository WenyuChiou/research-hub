import { useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { safeSourceUrl } from "./api";
import {
  BibtexIcon,
  BrandMark,
  CslJsonIcon,
  DestinationBrandChip,
  RisEndnoteIcon,
} from "./BrandIcons";
import { acquireModalBackgroundLock } from "./CommandPalette";
import { SyncHooksPanel } from "./SyncHooksBar";
import {
  buildApaBibliography,
  buildCiteKeyMap,
  buildCslJsonExport,
  buildObsidianBaseYaml,
  buildObsidianUri,
  buildRisExport,
  cleanBareDoi,
  makeCiteKey,
  resolveObsidianVaultName,
} from "./citations";
import { ErrorMessage } from "./components";
import { zhTW, type Translate } from "./i18n";
import type { IntegrationLiveState, Locale, ResearchRecord, Workspace } from "./types";
import { workingSummary } from "./WorkingSummaryEditor";

export type HandoffPresetId =
  | "zotero-obsidian"
  | "notebooklm-brief"
  | "seven-section-summary"
  | "triage-gap";

export type HandoffScope = "selected" | "filtered";
export type HandoffTab = "agent" | "sync" | "export";
export type DestinationState = "ok" | "configured" | "error" | "idle";

export interface HandoffTaskResult {
  id: string;
}

export const MAX_HANDOFF_TASK_CHARS = 20000;

export function computeDestinationStatuses(
  workspace?: Workspace | null,
  liveIntegrations?: IntegrationLiveState,
): { obsidian: DestinationState; zotero: DestinationState; notebooklm: DestinationState } {
  const localCap = liveIntegrations?.credentials ?? workspace?.capabilities?.local_integrations;

  const obsidian: DestinationState = liveIntegrations?.obsidian
    ? liveIntegrations.obsidian.status === "valid"
      ? "ok"
      : "error"
    : workspace?.capabilities?.obsidian_validation?.status === "available"
      ? "configured"
      : "idle";

  const zotero: DestinationState = liveIntegrations?.zotero
    ? ["connected_local_and_web", "connected_web", "connected_local"].includes(
        liveIntegrations.zotero.status,
      )
      ? "ok"
      : "error"
    : localCap?.zotero_configured
      ? "configured"
      : "idle";

  const notebooklm: DestinationState = liveIntegrations?.notebooklm
    ? liveIntegrations.notebooklm.status === "authenticated"
      ? "ok"
      : "error"
    : localCap?.nlm_state_present
      ? "configured"
      : "idle";

  return { obsidian, zotero, notebooklm };
}

const text = (value: unknown) =>
  typeof value === "string" || typeof value === "number" ? String(value) : "";

function strings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function collectAuthors(value: unknown): string[] {
  if (typeof value === "string") {
    return value.trim() ? [value.trim()] : [];
  }
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (typeof item === "string") return item.trim();
      if (item && typeof item === "object") {
        const obj = item as Record<string, unknown>;
        const direct = text(obj.name).trim();
        if (direct) return direct;
        return [text(obj.family).trim(), text(obj.given).trim()]
          .filter(Boolean)
          .join(", ");
      }
      return "";
    })
    .filter(Boolean);
}

function dedupeCaseInsensitive(values: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of values) {
    const cleaned = raw.trim().replace(/^#+/, "").trim();
    if (!cleaned) continue;
    const key = cleaned.toLocaleLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      out.push(cleaned);
    }
  }
  return out;
}

function collectTags(record: ResearchRecord): string[] {
  return dedupeCaseInsensitive([...strings(record.data.tags), ...strings(record.data.labels)]);
}

function rawScope(record: ResearchRecord): string {
  return (
    text(record.data.reading_level).trim() ||
    text(record.data.reading_scope).trim() ||
    "unknown"
  );
}

function savedSummary(record: ResearchRecord): string {
  return (
    [record.data.summary, record.data.abstract].find(
      (value): value is string => typeof value === "string" && Boolean(value.trim()),
    ) || ""
  );
}

function categorySlug(record: ResearchRecord): string {
  return text(record.data.category).trim() || text(record.data.sub_category).trim();
}

function yamlQuote(value: string): string {
  const cleaned = value.replace(/[\r\n\u0085\u2028\u2029]+/g, " ").trim();
  return JSON.stringify(cleaned);
}

function inlineMarkdown(value: string): string {
  return value
    .replace(/[\r\n\u0085\u2028\u2029]+/g, " ")
    .replace(/`/g, "'")
    .trim();
}

export function shellQuote(value: string): string {
  const cleaned = value.replace(/[\r\n\u0085\u2028\u2029]+/g, " ").trim();
  return `'${cleaned.replace(/'/g, "'\\''")}'`;
}

const BIBTEX_SPECIAL: Record<string, string> = {
  "\\": "\\textbackslash{}",
  "{": "\\{",
  "}": "\\}",
  "%": "\\%",
  "&": "\\&",
  "#": "\\#",
  $: "\\$",
  _: "\\_",
  "~": "\\textasciitilde{}",
  "^": "\\textasciicircum{}",
};

export function bibtexEscape(value: string): string {
  return value
    .replace(/[\r\n\u0085\u2028\u2029]+/g, " ")
    .trim()
    .replace(/[\\{}%&#$_~^]/g, (ch) => BIBTEX_SPECIAL[ch] ?? ch);
}

function bibtexVerbatim(value: string): string {
  return value
    .replace(/[\r\n\u0085\u2028\u2029]+/g, " ")
    .replace(/[{}\\]/g, "")
    .trim();
}

export function buildObsidianMarkdown(
  records: ResearchRecord[],
  screenings: Map<string, "include" | "exclude" | null>,
  projectTitle?: string,
  clusterSlug?: string,
): string {
  const safeCluster =
    (clusterSlug || "research-hub")
      .replace(/[^a-z0-9-_]/gi, "-")
      .toLowerCase() || "research-hub";
  if (records.length === 1) {
    const record = records[0];
    const authors = collectAuthors(record.data.authors);
    const tags = collectTags(record);
    const cat = categorySlug(record);
    const doi = cleanBareDoi(record.data.doi);
    const url =
      record.data.locator_kind !== "local-copy"
        ? safeSourceUrl(record.data.locator) || ""
        : "";
    const venue = text(record.data.venue).trim() || text(record.data.journal).trim();
    const year = text(record.data.year).trim();
    const scope = rawScope(record);
    const decision = screenings.get(record.id) ?? "unscreened";
    const identity = text(record.data.identity_status).trim() || "unverified";
    const summary = savedSummary(record);
    const working = workingSummary(record)?.text ?? "";
    const relevance = text(record.data.relevance).trim();

    const frontmatter = [
      "---",
      `title: ${yamlQuote(text(record.data.title))}`,
      `topic_cluster: ${yamlQuote(safeCluster)}`,
      `authors: [${authors.map(yamlQuote).join(", ")}]`,
      `year: ${year ? yamlQuote(year) : '""'}`,
      `venue: ${yamlQuote(venue)}`,
      `doi: ${yamlQuote(doi)}`,
      `url: ${yamlQuote(url)}`,
      `category: ${yamlQuote(cat)}`,
      `tags: [${tags.map(yamlQuote).join(", ")}]`,
      `reading_scope: ${yamlQuote(scope)}`,
      `screening: ${yamlQuote(decision)}`,
      `identity_status: ${yamlQuote(identity)}`,
      "---",
    ].join("\n");

    const sections = [
      `# ${inlineMarkdown(text(record.data.title))}`,
      "",
      `> Reading scope: \`${inlineMarkdown(scope)}\` · Screening: \`${inlineMarkdown(decision)}\` · Identity: \`${inlineMarkdown(identity)}\``,
      "",
      "## Summary",
      summary || "_No summary recorded yet._",
      ...(working
        ? ["", "## Working Summary (Unverified Draft)", working]
        : []),
      "",
      "## Relevance",
      relevance || "_No relevance note recorded yet._",
    ];
    return `${frontmatter}\n\n${sections.join("\n")}\n`;
  }

  const allTags = dedupeCaseInsensitive(records.flatMap(collectTags));
  const decisions = new Set(records.map((r) => screenings.get(r.id) ?? "unscreened"));
  const bundleScreening = decisions.size === 1 ? [...decisions][0] : "mixed";
  const frontmatter = [
    "---",
    `title: ${yamlQuote(`${projectTitle || "Research Hub"} — Literature Export (${records.length})`)}`,
    `topic_cluster: ${yamlQuote(safeCluster)}`,
    `category: "bundle"`,
    `reading_scope: "bundle"`,
    `screening: ${yamlQuote(bundleScreening)}`,
    `paper_count: ${records.length}`,
    `tags: [${allTags.map(yamlQuote).join(", ")}]`,
    "---",
  ].join("\n");

  const blocks = records.map((record, index) => {
    const authors = collectAuthors(record.data.authors).join(", ");
    const tags = collectTags(record);
    const cat = categorySlug(record) || "unclassified";
    const doi = text(record.data.doi).trim();
    const url =
      record.data.locator_kind !== "local-copy"
        ? safeSourceUrl(record.data.locator) || ""
        : "";
    const year = text(record.data.year).trim() || "n.d.";
    const scope = rawScope(record);
    const decision = screenings.get(record.id) ?? "unscreened";
    const summary = savedSummary(record);
    const working = workingSummary(record)?.text ?? "";
    const relevance = text(record.data.relevance).trim();
    return [
      `## ${index + 1}. ${inlineMarkdown(text(record.data.title))} (${inlineMarkdown(year)})`,
      `- **Authors**: ${inlineMarkdown(authors) || "—"}`,
      `- **Category**: \`${inlineMarkdown(cat)}\` · **Reading scope**: \`${inlineMarkdown(scope)}\` · **Screening**: \`${inlineMarkdown(decision)}\``,
      tags.length ? `- **Tags**: ${tags.map((tag) => `#${inlineMarkdown(tag).replace(/\s+/g, "-")}`).join(" ")}` : null,
      doi ? `- **DOI**: \`${inlineMarkdown(doi)}\`` : null,
      url ? `- **Source**: ${url}` : null,
      summary ? `\n${summary}` : null,
      working ? `\n### Working Summary (Unverified Draft)\n${working}` : null,
      relevance ? `\n**Relevance**: ${relevance}` : null,
    ]
      .filter(Boolean)
      .join("\n");
  });

  return `${frontmatter}\n\n# ${inlineMarkdown(projectTitle || "Research Hub")} — Literature Bundle (${records.length})\n\n${blocks.join("\n\n---\n\n")}\n`;
}

export function buildNotebookLmSourcePack(
  records: ResearchRecord[],
  projectTitle?: string,
  projectId?: string,
): string {
  const fullText = records.filter((r) => rawScope(r) === "full-text");
  const abstractOrPartial = records.filter((r) => rawScope(r) !== "full-text");
  const slug = (projectId || "research-cluster").replace(/[^a-z0-9-]/gi, "-").toLowerCase();

  const renderEntry = (record: ResearchRecord, index: number) => {
    const authors = collectAuthors(record.data.authors).join(", ");
    const year = text(record.data.year).trim() || "n.d.";
    const doi = text(record.data.doi).trim();
    const scope = rawScope(record);
    const tags = collectTags(record);
    const summary = savedSummary(record);
    const working = workingSummary(record)?.text ?? "";
    const relevance = text(record.data.relevance).trim();
    return [
      `### ${index + 1}. ${inlineMarkdown(text(record.data.title))} (${inlineMarkdown(year)})`,
      `- Authors: ${inlineMarkdown(authors) || "Unknown"}`,
      `- Reading Scope: ${inlineMarkdown(scope)}`,
      `- Category: ${inlineMarkdown(categorySlug(record) || "unclassified")}`,
      tags.length ? `- Keywords/Labels: ${tags.map(inlineMarkdown).join(", ")}` : null,
      doi ? `- DOI: ${inlineMarkdown(doi)}` : null,
      summary ? `\n${summary}` : "\n[No abstract or summary saved locally.]",
      working ? `\n#### Working Summary (Unverified Draft)\n${working}` : null,
      relevance ? `\nRelevance note: ${relevance}` : null,
    ]
      .filter(Boolean)
      .join("\n");
  };

  return [
    `# NotebookLM Source Pack: ${inlineMarkdown(projectTitle || "Research Hub Literature")}`,
    "",
    "> **Evidence-Boundary Notice for NotebookLM**:",
    `> - Full-text declared sources: ${fullText.length}`,
    `> - Abstract / metadata-only / unknown-scope sources: ${abstractOrPartial.length}`,
    "> - Do NOT attribute detailed experimental methods, sample sizes, or p-values to abstract-only or metadata-only items unless verified in full text.",
    "",
    "## CLI Cluster & NotebookLM Commands",
    "> Upload this `.md` file directly to NotebookLM, or prepare a dedicated pipeline cluster for ONLY these papers before bundling:",
    "```bash",
    `# 1. Create (or reuse) a dedicated pipeline cluster for this selection:`,
    `research-hub clusters new --query ${shellQuote(projectTitle || slug)} --slug ${slug}`,
    `# 2. Preview ingesting ONLY the selected papers JSON, then re-run without --dry-run on approval:`,
    `research-hub ingest --input <papers.json> --cluster ${slug} --dry-run`,
    `# 3. Bundle the ingested cluster and preview NotebookLM upload:`,
    `research-hub notebooklm bundle --cluster ${slug}`,
    `research-hub notebooklm upload --cluster ${slug} --dry-run`,
    `# After inspecting dry-run output:`,
    `research-hub notebooklm upload --cluster ${slug} --create-if-missing`,
    "```",
    "",
    `## Full-Text Declared Sources (${fullText.length})`,
    fullText.length
      ? fullText.map(renderEntry).join("\n\n")
      : "_None in the current selection. Attach or ingest full-text PDFs before generating full-text NotebookLM claims._",
    "",
    `## Abstract-Only & Metadata Sources (${abstractOrPartial.length})`,
    abstractOrPartial.length
      ? abstractOrPartial.map(renderEntry).join("\n\n")
      : "_None._",
    "",
  ].join("\n");
}

export function buildBibtexExport(
  records: ResearchRecord[],
  citeKeyMap?: ReadonlyMap<string, string>,
): string {
  const resolvedKeys = citeKeyMap ?? buildCiteKeyMap(records);
  const usedKeys = new Set<string>();
  return (
    records
      .map((record, index) => {
        let key = resolvedKeys.get(record.id) || makeCiteKey(record, index);
        if (usedKeys.has(key)) {
          let suffix = 2;
          while (usedKeys.has(`${key}_${suffix}`)) suffix++;
          key = `${key}_${suffix}`;
        }
        usedKeys.add(key);
        const authors = collectAuthors(record.data.authors).join(" and ");
        const venue = text(record.data.venue).trim() || text(record.data.journal).trim();
        const year = text(record.data.year).trim();
        const doi = cleanBareDoi(record.data.doi);
        const url =
          record.data.locator_kind !== "local-copy"
            ? safeSourceUrl(record.data.locator) || ""
            : "";
        const tags = dedupeCaseInsensitive([categorySlug(record), ...collectTags(record)].filter(Boolean));
        const summary = savedSummary(record);
        const scope = rawScope(record);
        const identity = text(record.data.identity_status).trim() || "unverified";
        const fields: [string, string][] = [
          ["title", bibtexEscape(text(record.data.title))],
          authors ? ["author", bibtexEscape(authors)] : ["", ""],
          year ? ["year", bibtexVerbatim(year)] : ["", ""],
          venue ? ["journal", bibtexEscape(venue)] : ["", ""],
          doi ? ["doi", bibtexVerbatim(doi)] : ["", ""],
          url ? ["url", bibtexVerbatim(url)] : ["", ""],
          tags.length ? ["keywords", bibtexEscape(tags.join(", "))] : ["", ""],
          summary ? ["abstract", bibtexEscape(summary)] : ["", ""],
          ["note", bibtexEscape(`Reading scope: ${scope}; Identity: ${identity}`)],
        ].filter(([k, v]) => Boolean(k && v)) as [string, string][];

        return `@article{${key},\n${fields.map(([k, v]) => `  ${k} = {${v}}`).join(",\n")}\n}`;
      })
      .join("\n\n") + "\n"
  );
}

export function buildAgentHandoffPrompt({
  preset,
  records,
  screenings,
  projectId,
  projectTitle,
  locale,
  maxChars,
}: {
  preset: HandoffPresetId;
  records: ResearchRecord[];
  screenings: Map<string, "include" | "exclude" | null>;
  projectId?: string;
  projectTitle?: string;
  locale: Locale;
  maxChars?: number;
}): { operation: "synthesize" | "frame"; prompt: string; truncatedCount: number } {
  const pid = projectId || "<project-id>";
  const clusterSlug = (projectId || "selected-cluster").replace(/[^a-z0-9-]/gi, "-").toLowerCase();
  const fullTextCount = records.filter((r) => rawScope(r) === "full-text").length;
  const abstractCount = records.length - fullTextCount;
  const paperLines = records.map((record, index) => {
    const year = text(record.data.year).trim() || "n.d.";
    const cat = categorySlug(record) || "unclassified";
    const scope = rawScope(record);
    const doi = text(record.data.doi).trim();
    const url =
      record.data.locator_kind !== "local-copy"
        ? safeSourceUrl(record.data.locator) || ""
        : "";
    const tags = collectTags(record);
    const decision = screenings.get(record.id) ?? "unscreened";
    const parts = [
      `${index + 1}. "${inlineMarkdown(text(record.data.title))}" (${inlineMarkdown(year)})`,
      `source_id=${record.id}`,
      `category=${inlineMarkdown(cat)}`,
      `reading_scope=${inlineMarkdown(scope)}`,
      `screening=${decision}`,
      tags.length ? `labels=[${tags.map(inlineMarkdown).join(", ")}]` : null,
      doi ? `doi=${inlineMarkdown(doi)}` : null,
      url ? `url=${url}` : null,
    ].filter(Boolean);
    return parts.join(" | ");
  });

  const isZh = locale === "zh-TW";
  const header = isZh
    ? [
        `# Research Hub AI 助理交接指令`,
        `- 專案：${inlineMarkdown(projectTitle || pid)} (\`${pid}\`)`,
        `- 目標文獻：${records.length} 篇（全文宣告：${fullTextCount}，僅摘要／書目／未知：${abstractCount}）`,
        "",
      ]
    : [
        `# Research Hub AI Agent Handoff`,
        `- Project: ${inlineMarkdown(projectTitle || pid)} (\`${pid}\`)`,
        `- Target sources: ${records.length} (${fullTextCount} full-text declared, ${abstractCount} abstract/metadata/unknown)`,
        "",
      ];

  let instructions: string[];
  let operation: "synthesize" | "frame" = "synthesize";

  if (preset === "zotero-obsidian") {
    instructions = isZh
      ? [
          "## 任務目標：轉換並同步至 Zotero 與 Obsidian",
          "1. 先為下列文獻驗證 DOI / 書目身分，保留 `category`、`labels`（關鍵字標籤）與 `reading_scope`（切勿將 `abstract` 或 `metadata` 誤標為 `full-text`）。",
          "2. 確認或建立目標群組（`research-hub clusters new --query \"<topic>\" --slug <cluster-slug>`），產出標準 ingest JSON 後**先執行 dry-run 預覽**：",
          `   \`research-hub ingest --input <papers.json> --cluster ${clusterSlug} --dry-run\``,
          "3. 將 dry-run 差異（新增／略過／標籤／分類）回報給我確認；**獲得明確核准後**才移除 `--dry-run` 寫入 Zotero 與 Obsidian Vault（若本機已啟用 Obsidian v1.12+ 官方 CLI 或 `obsidianmd/obsidian-skills`，亦可在核准後透過官方 CLI 更新索引與 Bases 檢視）。",
          "4. 同步完成後，可協助執行 `scripts/library_snapshot.py --vault <vault> --collection <cluster-slug> --output <snapshot.json>` 更新唯讀快照。",
        ]
      : [
          "## Task: Convert & Sync to Zotero + Obsidian",
          "1. Verify DOI / bibliographic identity for the sources below while preserving `category`, `labels`, and `reading_scope` (NEVER promote `abstract` or `metadata` items to `full-text`).",
          "2. Create or confirm the target cluster (`research-hub clusters new --query \"<topic>\" --slug <cluster-slug>`), prepare the ingest JSON, and run a **dry-run preview first**:",
          `   \`research-hub ingest --input <papers.json> --cluster ${clusterSlug} --dry-run\``,
          "3. Report the dry-run diff (adds / skips / categories / labels) and **wait for my explicit approval** before re-running without `--dry-run` to write to Zotero or Obsidian (if Obsidian v1.12+ official CLI or `obsidianmd/obsidian-skills` is enabled, use it after approval so Wikilinks and Obsidian Bases stay indexed).",
          "4. After approval and ingest, refresh the read-only UI snapshot via `scripts/library_snapshot.py --vault <vault> --collection <cluster-slug> --output <snapshot.json>`.",
        ];
  } else if (preset === "notebooklm-brief") {
    instructions = isZh
      ? [
          "## 任務目標：打包送進 NotebookLM 並驗證簡報",
          "1. 先區分下列文獻哪些已有全文 PDF、哪些僅有摘要（Abstract only）；對僅摘要文獻明確標示證據邊界，不可將摘要推論當作全文方法。",
          "2. 注意工作區專案不等於管線 Cluster：請先建立或指定專用 Cluster，並將**僅限此次選定的文獻**透過 dry-run 審核後匯入該 Cluster（或直接上傳匯出的 NotebookLM 來源包 `.md`）：",
          `   \`research-hub clusters new --query "<topic>" --slug ${clusterSlug}\``,
          `   \`research-hub ingest --input <papers.json> --cluster ${clusterSlug} --dry-run\``,
          "3. 確認該 Cluster 僅含選定文獻後，執行打包與乾跑預覽：",
          `   \`research-hub notebooklm bundle --cluster ${clusterSlug}\``,
          `   \`research-hub notebooklm upload --cluster ${clusterSlug} --dry-run\``,
          "4. 檢查 NotebookLM 登入狀態（`research-hub doctor`）；經我確認後才加上 `--create-if-missing` 上傳並產生簡報，最後用 `notebooklm-brief-verifier` 核對每條引用。",
        ]
      : [
          "## Task: Prepare NotebookLM Bundle & Verify Brief",
          "1. Separate full-text PDF sources from abstract-only / metadata-only sources below and explicitly mark evidence boundaries.",
          "2. Workspace projects are separate from pipeline clusters: create or pick a dedicated cluster for ONLY these selected papers (or upload the exported NotebookLM Source Pack `.md` directly):",
          `   \`research-hub clusters new --query "<topic>" --slug ${clusterSlug}\``,
          `   \`research-hub ingest --input <papers.json> --cluster ${clusterSlug} --dry-run\``,
          "3. After confirming the cluster holds only the intended papers, bundle and preview upload first (never upload without showing dry-run output):",
          `   \`research-hub notebooklm bundle --cluster ${clusterSlug}\``,
          `   \`research-hub notebooklm upload --cluster ${clusterSlug} --dry-run\``,
          "4. Check NotebookLM session health via `research-hub doctor`; after my approval, upload with `--create-if-missing`, generate the brief, and audit every citation with `notebooklm-brief-verifier`.",
        ];
  } else if (preset === "seven-section-summary") {
    instructions = isZh
      ? [
          "## 任務目標：精讀並產出 7 段結構化摘要（paper-summarize）",
          "1. 依據每篇文獻的實際可讀範圍（`reading_scope`）使用 `paper-summarize` 產出 7 段結構化摘要（研究緣由／目的／方法／發現／結論／重點／限制），並附上原文引句與 `supported` / `inference` / `unknown` 標記。",
          "2. 若文獻僅為 `abstract` 或 `metadata`，未提及的方法／限制必須誠實標記為 `unknown`，不可腦補。",
          `3. 產出符合規格的摘要封包 JSON（內含對應 \`source_id\`）後，透過以下指令匯入 Research Hub 供我人工審閱：`,
          `   \`research-hub project native-summary-import --root <workspace-root> --project ${pid} --path <relative-envelope.json>\``,
        ]
      : [
          "## Task: Generate 7-Section Structured Summaries (`paper-summarize`)",
          "1. Using each paper's true `reading_scope`, run `paper-summarize` to draft a 7-section structured summary with verbatim evidence quotes and `supported` / `inference` / `unknown` labels.",
          "2. For `abstract` or `metadata` items, mark unstated methods/limitations honestly as `unknown`—never invent full-text claims.",
          `3. Write the authored summary envelope JSON (binding each target \`source_id\`) under the workspace root and import for human review via:`,
          `   \`research-hub project native-summary-import --root <workspace-root> --project ${pid} --path <relative-envelope.json>\``,
        ];
  } else {
    operation = "frame";
    instructions = isZh
      ? [
          "## 任務目標：建立文獻比較矩陣並找出研究缺口",
          "1. 針對下列已篩選的文獻群組，使用 `literature-triage-matrix` 建立比較表（研究問題、方法、資料集、關鍵限制、閱讀範圍、標籤）。",
          "2. 使用 `gap-to-topic` 歸納 2–3 個有證據支撐的研究缺口（標明支撐文獻 `source_id` 與證據限制），不得將 `abstract-only` 推論寫成已驗證定論。",
          "3. 產出結果後交由我在 Research Hub 審查與納入研究問題／證據台帳。",
        ]
      : [
          "## Task: Build Literature Triage Matrix & Research Gaps",
          "1. Run `literature-triage-matrix` over the filtered cohort below (question, method, dataset, limitations, reading scope, labels).",
          "2. Run `gap-to-topic` to propose 2–3 evidence-grounded research gaps citing exact `source_id` entries and noting any `abstract-only` caveats.",
          "3. Return the draft for human review before recording claims into the Research Hub evidence ledger.",
        ];
  }

  const listHeading = isZh ? "## 文獻清單" : "## Selected Sources";
  const prefix = [...header, ...instructions, "", listHeading].join("\n");

  if (maxChars === undefined) {
    return {
      operation,
      prompt: [prefix, ...paperLines].join("\n"),
      truncatedCount: 0,
    };
  }

  const fullText = [prefix, ...paperLines].join("\n");
  if (fullText.length <= maxChars) {
    return { operation, prompt: fullText, truncatedCount: 0 };
  }

  const reserve = 220;
  const budget = Math.max(prefix.length + 1, maxChars - reserve);
  const kept: string[] = [];
  let currentLen = prefix.length;
  for (const line of paperLines) {
    if (currentLen + 1 + line.length > budget) break;
    kept.push(line);
    currentLen += 1 + line.length;
  }
  const omitted = paperLines.length - kept.length;
  const suffix = isZh
    ? `\n…（為符合 20,000 字元上限，略去其餘 ${omitted} 篇摘要列；所有選定的工作區文獻紀錄仍完整綁定於 packet.json 的 records 與 selected_source_ids。）`
    : `\n… (${omitted} additional source line(s) omitted to stay within the 20,000-char limit; all selected workspace source records remain bound in packet.json records & selected_source_ids.)`;
  const bounded = ([prefix, ...kept].join("\n") + suffix).slice(0, maxChars);
  return { operation, prompt: bounded, truncatedCount: omitted };
}

function downloadTextFile(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const FOCUSABLE_SELECTOR =
  'a[href], button:not(:disabled), textarea:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex="-1"])';

export function AgentHandoffModal({
  open,
  initialScope,
  selectedRecord,
  filteredRecords,
  screenings,
  projectId,
  projectTitle,
  workspace,
  liveIntegrations,
  locale: explicitLocale,
  t,
  onClose,
  onCreateHandoffTask,
  onNavigateReview,
  onOpenSetup,
  onCopyMasterMarkdown,
  onExportMasterCsv,
}: {
  open: boolean;
  initialScope: HandoffScope;
  selectedRecord?: ResearchRecord;
  filteredRecords: ResearchRecord[];
  screenings: Map<string, "include" | "exclude" | null>;
  projectId?: string;
  projectTitle?: string;
  workspace?: Workspace | null;
  liveIntegrations?: IntegrationLiveState;
  locale?: Locale;
  t: Translate;
  onClose: () => void;
  onCreateHandoffTask?: (payload: {
    operation: "synthesize" | "frame";
    instructions: string;
    selected_source_ids?: string[];
  }) => Promise<HandoffTaskResult>;
  onNavigateReview?: (taskId?: string) => void;
  onOpenSetup?: () => void;
  onCopyMasterMarkdown?: (records?: ResearchRecord[]) => Promise<boolean>;
  onExportMasterCsv?: (records?: ResearchRecord[]) => void;
}) {
  const dialogId = useId();
  const backdropRef = useRef<HTMLDivElement>(null);
  const modalRef = useRef<HTMLElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const wasOpenRef = useRef(false);

  const [tab, setTab] = useState<HandoffTab>("agent");
  const [scope, setScope] = useState<HandoffScope>(
    initialScope === "selected" && selectedRecord ? "selected" : "filtered",
  );
  const [preset, setPreset] = useState<HandoffPresetId>("zotero-obsidian");
  const [customPrompt, setCustomPrompt] = useState<string | null>(null);
  const [statusNote, setStatusNote] = useState<{ tone: "good" | "bad"; text: string } | null>(null);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<unknown>(null);
  const [createdTaskId, setCreatedTaskId] = useState<string | null>(null);

  const locale: Locale =
    explicitLocale ?? (t("handoffModalTitle") === zhTW.handoffModalTitle ? "zh-TW" : "en");

  // Initialize state and capture trigger focus ONLY on closed -> open transition (never on background refreshes).
  useEffect(() => {
    const justOpened = open && !wasOpenRef.current;
    wasOpenRef.current = open;
    if (!justOpened) return;
    previousFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setScope(initialScope === "selected" && selectedRecord ? "selected" : "filtered");
    setCustomPrompt(null);
    setStatusNote(null);
    setCreateError(null);
    setCreatedTaskId(null);
    const frame = requestAnimationFrame(() => headingRef.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [open, initialScope, selectedRecord?.id]);

  // If the currently selected paper disappears while open, fall back cleanly to filtered set.
  useEffect(() => {
    if (open && scope === "selected" && !selectedRecord) {
      setScope("filtered");
    }
  }, [open, scope, selectedRecord]);

  // Background inertness + focus restoration on close/unmount (reference-counted with CommandPalette).
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const suppressFocusRestoreRef = useRef(false);
  useEffect(() => {
    if (!open) return;
    suppressFocusRestoreRef.current = false;
    const handleDismissOverlays = () => {
      suppressFocusRestoreRef.current = true;
      onCloseRef.current();
    };
    window.addEventListener("research-hub:dismiss-overlays", handleDismissOverlays);
    const releaseBackground = acquireModalBackgroundLock(backdropRef.current);
    return () => {
      window.removeEventListener("research-hub:dismiss-overlays", handleDismissOverlays);
      releaseBackground();
      const prev = previousFocusRef.current;
      if (!suppressFocusRestoreRef.current && prev && prev.isConnected && !prev.closest("[inert]")) {
        prev.focus();
      }
    };
  }, [open]);

  // Escape dismissal & Tab/Shift+Tab focus containment inside modal.
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (backdropRef.current?.hasAttribute("inert")) return;
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key === "Tab" && modalRef.current) {
        const focusables = Array.from(
          modalRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
        ).filter((el) => el.offsetParent !== null || el === document.activeElement);
        if (!focusables.length) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const active = document.activeElement as HTMLElement | null;
        if (event.shiftKey) {
          if (!active || active === first || active === headingRef.current || !modalRef.current.contains(active)) {
            event.preventDefault();
            last.focus();
          }
        } else if (!active || active === last || !modalRef.current.contains(active)) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  const targetRecords = useMemo(() => {
    if (scope === "selected" && selectedRecord) return [selectedRecord];
    return filteredRecords;
  }, [scope, selectedRecord, filteredRecords]);

  const workspaceSourceIds = useMemo(
    () => targetRecords.filter((r) => r.kind === "source").map((r) => r.id),
    [targetRecords],
  );

  const generated = useMemo(
    () =>
      buildAgentHandoffPrompt({
        preset,
        records: targetRecords,
        screenings,
        projectId,
        projectTitle,
        locale,
      }),
    [preset, targetRecords, screenings, projectId, projectTitle, locale],
  );

  const boundedTaskPrompt = useMemo(
    () =>
      buildAgentHandoffPrompt({
        preset,
        records: targetRecords,
        screenings,
        projectId,
        projectTitle,
        locale,
        maxChars: MAX_HANDOFF_TASK_CHARS,
      }),
    [preset, targetRecords, screenings, projectId, projectTitle, locale],
  );

  const effectivePrompt = customPrompt ?? generated.prompt;
  const userEditedTooLong =
    customPrompt !== null && customPrompt.length > MAX_HANDOFF_TASK_CHARS;
  const autoWillTruncate =
    customPrompt === null && generated.prompt.length > MAX_HANDOFF_TASK_CHARS;
  const fullTextCount = targetRecords.filter((r) => rawScope(r) === "full-text").length;
  const abstractOnlyCount = targetRecords.length - fullTextCount;

  if (!open) return null;

  const dest = computeDestinationStatuses(workspace, liveIntegrations);

  async function copyText(content: string, successMessage: string) {
    if (!navigator.clipboard?.writeText) {
      setStatusNote({ tone: "bad", text: t("handoffCopyFailed") });
      return;
    }
    try {
      await navigator.clipboard.writeText(content);
      setStatusNote({ tone: "good", text: successMessage });
    } catch {
      setStatusNote({ tone: "bad", text: t("handoffCopyFailed") });
    }
  }

  async function handleCreateTask() {
    if (
      !onCreateHandoffTask ||
      creating ||
      !workspaceSourceIds.length ||
      userEditedTooLong
    ) {
      return;
    }
    setCreating(true);
    setCreateError(null);
    setStatusNote(null);
    try {
      const instructions =
        customPrompt !== null ? customPrompt : boundedTaskPrompt.prompt;
      const created = await onCreateHandoffTask({
        operation: generated.operation,
        instructions,
        selected_source_ids: workspaceSourceIds,
      });
      setCreatedTaskId(created.id);
      setStatusNote({ tone: "good", text: t("handoffTaskCreated") });
    } catch (failure) {
      setCreateError(failure);
    } finally {
      setCreating(false);
    }
  }

  const slugBase = (projectId || "research-hub").replace(/[^a-z0-9-_]/gi, "-");
  const obsidianVaultName = resolveObsidianVaultName(workspace, liveIntegrations);
  const obsidianAppUri = buildObsidianUri(obsidianVaultName);
  const exportKeyMap = useMemo(
    () => buildCiteKeyMap(filteredRecords.length ? filteredRecords : targetRecords),
    [filteredRecords, targetRecords],
  );

  const presets: { id: HandoffPresetId; title: string; desc: string }[] = [
    {
      id: "zotero-obsidian",
      title: t("handoffPresetSyncTitle"),
      desc: t("handoffPresetSyncDesc"),
    },
    {
      id: "notebooklm-brief",
      title: t("handoffPresetNlmTitle"),
      desc: t("handoffPresetNlmDesc"),
    },
    {
      id: "seven-section-summary",
      title: t("handoffPresetSummaryTitle"),
      desc: t("handoffPresetSummaryDesc"),
    },
    {
      id: "triage-gap",
      title: t("handoffPresetMatrixTitle"),
      desc: t("handoffPresetMatrixDesc"),
    },
  ];

  const statusText = (state: DestinationState) =>
    state === "ok"
      ? t("pipelineStatusOk")
      : state === "configured"
        ? t("pipelineStatusConfigured")
        : state === "error"
          ? t("pipelineStatusError")
          : onOpenSetup
            ? t("pipelineStatusIdle")
            : t("pipelineStatusIdleReadOnly");

  return createPortal(
    <div
      ref={backdropRef}
      className="handoff-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        ref={modalRef}
        id={dialogId}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${dialogId}-title`}
        className="handoff-modal"
      >
        <header className="handoff-modal-header">
          <div>
            <h2 ref={headingRef} id={`${dialogId}-title`} tabIndex={-1}>
              {t("handoffModalTitle")}
            </h2>
            <p className="small muted">{t("handoffModalSubtitle")}</p>
          </div>
          <button
            type="button"
            className="button secondary small icon-btn"
            onClick={onClose}
            aria-label={t("integrationClose")}
            data-tooltip={t("integrationClose")}
            data-tooltip-pos="bottom-end"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true" focusable="false">
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          </button>
        </header>

        <div className="handoff-context-strip">
          <div className="handoff-scope-switch" role="group" aria-label={t("handoffScopeLabel")}>
            {selectedRecord && (
              <button
                type="button"
                aria-pressed={scope === "selected"}
                onClick={() => {
                  setScope("selected");
                  setCustomPrompt(null);
                  setCreatedTaskId(null);
                }}
              >
                {t("handoffScopeSelected")} (1)
              </button>
            )}
            <button
              type="button"
              aria-pressed={scope === "filtered"}
              onClick={() => {
                setScope("filtered");
                setCustomPrompt(null);
                setCreatedTaskId(null);
              }}
            >
              {t("handoffScopeFiltered")} ({filteredRecords.length})
            </button>
          </div>
          <div className="handoff-boundary-chips">
            <span className="scope-pill scope-full">
              {t("catalogFullTextDeclared")}: {fullTextCount}
            </span>
            <span className="scope-pill scope-abstract">
              {t("handoffAbstractOrMetaCount")}: {abstractOnlyCount}
            </span>
          </div>
        </div>

        <div className="handoff-tabs" role="tablist" aria-label={t("handoffModalTitle")}>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "agent"}
            onClick={() => setTab("agent")}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
              <path d="M12 3v4" />
              <path d="M12 17v4" />
              <path d="m4.93 4.93 2.83 2.83" />
              <path d="m16.24 16.24 2.83 2.83" />
              <path d="M3 12h4" />
              <path d="M17 12h4" />
              <circle cx="12" cy="12" r="3" />
            </svg>
            <span>{t("handoffTabAgent")}</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "sync"}
            onClick={() => setTab("sync")}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
              <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
              <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
            </svg>
            <span>{t("handoffTabSync")}</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "export"}
            onClick={() => setTab("export")}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            <span>{t("handoffTabExport")}</span>
          </button>
        </div>

        <div className="handoff-modal-body">
          <div className="handoff-dest-bar" role="group" aria-label={t("handoffPipelineReadiness")}>
            <DestinationBrandChip
              brand="obsidian"
              state={dest.obsidian}
              statusText={statusText(dest.obsidian)}
              tooltipPos="bottom-start"
              onClick={
                onOpenSetup
                  ? () => {
                      onClose();
                      onOpenSetup();
                    }
                  : undefined
              }
            />
            <DestinationBrandChip
              brand="zotero"
              state={dest.zotero}
              statusText={statusText(dest.zotero)}
              tooltipPos="bottom-start"
              onClick={
                onOpenSetup
                  ? () => {
                      onClose();
                      onOpenSetup();
                    }
                  : undefined
              }
            />
            <DestinationBrandChip
              brand="notebooklm"
              state={dest.notebooklm}
              statusText={statusText(dest.notebooklm)}
              tooltipPos="bottom-start"
              onClick={
                onOpenSetup
                  ? () => {
                      onClose();
                      onOpenSetup();
                    }
                  : undefined
              }
            />
            {onOpenSetup && (
              <button
                type="button"
                className="button text-button small"
                onClick={() => {
                  onClose();
                  onOpenSetup();
                }}
              >
                {t("handoffConfigureConnections")}
              </button>
            )}
          </div>

          {tab === "agent" ? (
            <div className="handoff-agent-pane">
              <div className="handoff-preset-grid" role="group" aria-label={t("handoffPresetsLabel")}>
                {presets.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className="handoff-preset-card"
                    aria-pressed={preset === item.id}
                    onClick={() => {
                      setPreset(item.id);
                      setCustomPrompt(null);
                      setCreatedTaskId(null);
                      setStatusNote(null);
                    }}
                  >
                    <strong>{item.title}</strong>
                    <span>{item.desc}</span>
                  </button>
                ))}
              </div>
              <div className="handoff-prompt-box">
                <div className="handoff-prompt-label">
                  <label htmlFor={`${dialogId}-prompt`}>{t("handoffPromptLabel")}</label>
                  <span className="small muted">{t("handoffSafetyNote")}</span>
                </div>
                <textarea
                  id={`${dialogId}-prompt`}
                  rows={9}
                  value={effectivePrompt}
                  onChange={(e) => setCustomPrompt(e.target.value)}
                />
                {userEditedTooLong && (
                  <p role="alert" className="small bad-text">
                    {t("handoffTaskTooLong")} ({effectivePrompt.length.toLocaleString()} / {MAX_HANDOFF_TASK_CHARS.toLocaleString()})
                  </p>
                )}
                {autoWillTruncate && (
                  <p className="small muted">{t("handoffTaskTruncatedNote")}</p>
                )}
                {onCreateHandoffTask && targetRecords.length > 0 && workspaceSourceIds.length === 0 && (
                  <p className="small muted">{t("handoffReadOnlyNoTask")}</p>
                )}
              </div>
              <div className="handoff-actions">
                <button
                  type="button"
                  className="button primary"
                  disabled={!targetRecords.length}
                  onClick={() => void copyText(effectivePrompt, t("handoffPromptCopied"))}
                >
                  {t("handoffCopyPrompt")}
                </button>
                {onCreateHandoffTask && (
                  <button
                    type="button"
                    className="button secondary"
                    disabled={creating || !workspaceSourceIds.length || userEditedTooLong}
                    onClick={() => void handleCreateTask()}
                  >
                    {creating ? t("saving") : t("handoffCreateTask")}
                  </button>
                )}
                {createdTaskId && onNavigateReview && (
                  <button
                    type="button"
                    className="button secondary"
                    onClick={() => {
                      onClose();
                      onNavigateReview(createdTaskId);
                    }}
                  >
                    {t("handoffOpenInReview")} →
                  </button>
                )}
              </div>
              {createError !== null && createError !== undefined && (
                <ErrorMessage error={createError} t={t} />
              )}
            </div>
          ) : tab === "sync" ? (
            <SyncHooksPanel
              projectId={projectId}
              projectTitle={projectTitle}
              sources={targetRecords}
              selectedIds={workspaceSourceIds}
              workspace={workspace}
              liveIntegrations={liveIntegrations}
              locale={locale}
              onOpenSetup={
                onOpenSetup
                  ? () => {
                      onClose();
                      onOpenSetup();
                    }
                  : undefined
              }
            />
          ) : (
            <div className="handoff-export-grid">
              <article className="handoff-export-card">
                <div>
                  <h3 className="handoff-export-heading">
                    <span className="handoff-export-icon brand-obsidian" aria-hidden="true">
                      <BrandMark brand="obsidian" size={17} />
                    </span>
                    <span>{t("handoffExportObsidianTitle")}</span>
                  </h3>
                  <p className="small muted">{t("handoffExportObsidianDesc")}</p>
                </div>
                <div className="handoff-export-actions">
                  <button
                    type="button"
                    className="button primary small"
                    disabled={!targetRecords.length}
                    onClick={() => {
                      const md = buildObsidianMarkdown(targetRecords, screenings, projectTitle, slugBase);
                      downloadTextFile(
                        `${slugBase}-obsidian-${targetRecords.length === 1 ? "note" : "bundle"}.md`,
                        md,
                        "text/markdown;charset=utf-8",
                      );
                      setStatusNote({ tone: "good", text: t("handoffFileDownloaded") });
                    }}
                  >
                    {t("handoffDownloadMd")}
                  </button>
                  <button
                    type="button"
                    className="button secondary small"
                    disabled={!targetRecords.length}
                    onClick={() => {
                      const baseYaml = buildObsidianBaseYaml(slugBase, projectTitle, targetRecords);
                      downloadTextFile(
                        `${slugBase}.base`,
                        baseYaml,
                        "text/yaml;charset=utf-8",
                      );
                      setStatusNote({ tone: "good", text: t("handoffFileDownloaded") });
                    }}
                  >
                    {t("handoffDownloadBase")}
                  </button>
                  <button
                    type="button"
                    className="button secondary small"
                    disabled={!targetRecords.length}
                    onClick={() =>
                      void copyText(
                        buildObsidianMarkdown(targetRecords, screenings, projectTitle, slugBase),
                        t("handoffCopiedFile"),
                      )
                    }
                  >
                    {t("nativeCopyMarkdown")}
                  </button>
                  {obsidianAppUri && (
                    <a
                      className="button secondary small"
                      href={obsidianAppUri}
                      rel="noopener noreferrer"
                    >
                      {t("obsidianOpenApp")} <span aria-hidden="true">↗</span>
                    </a>
                  )}
                </div>
              </article>

              <article className="handoff-export-card">
                <div>
                  <h3 className="handoff-export-heading">
                    <span className="handoff-export-icon brand-notebooklm" aria-hidden="true">
                      <BrandMark brand="notebooklm" size={17} />
                    </span>
                    <span>{t("handoffExportNlmTitle")}</span>
                  </h3>
                  <p className="small muted">{t("handoffExportNlmDesc")}</p>
                </div>
                <div className="handoff-export-actions">
                  <button
                    type="button"
                    className="button primary small"
                    disabled={!targetRecords.length}
                    onClick={() => {
                      const pack = buildNotebookLmSourcePack(targetRecords, projectTitle, projectId);
                      downloadTextFile(
                        `${slugBase}-notebooklm-sources.md`,
                        pack,
                        "text/markdown;charset=utf-8",
                      );
                      setStatusNote({ tone: "good", text: t("handoffFileDownloaded") });
                    }}
                  >
                    {t("handoffDownloadNlmPack")}
                  </button>
                  <button
                    type="button"
                    className="button secondary small"
                    disabled={!targetRecords.length}
                    onClick={() =>
                      void copyText(
                        buildNotebookLmSourcePack(targetRecords, projectTitle, projectId),
                        t("handoffCopiedFile"),
                      )
                    }
                  >
                    {t("nativeCopyMarkdown")}
                  </button>
                </div>
              </article>

              <article className="handoff-export-card">
                <div>
                  <h3 className="handoff-export-heading">
                    <span className="handoff-export-icon brand-zotero" aria-hidden="true">
                      <BrandMark brand="zotero" size={17} />
                    </span>
                    <span>{t("handoffExportCitationsTitle")}</span>
                  </h3>
                  <p className="small muted">{t("handoffExportCitationsDesc")}</p>
                </div>
                <div className="handoff-export-actions">
                  <button
                    type="button"
                    className="button primary small"
                    disabled={!targetRecords.length}
                    onClick={() => {
                      const bib = buildBibtexExport(targetRecords, exportKeyMap);
                      downloadTextFile(
                        `${slugBase}-citations.bib`,
                        bib,
                        "application/x-bibtex;charset=utf-8",
                      );
                      setStatusNote({ tone: "good", text: t("handoffFileDownloaded") });
                    }}
                  >
                    <BibtexIcon size={14} />
                    <span>{t("handoffDownloadBib")}</span>
                  </button>
                  <button
                    type="button"
                    className="button secondary small"
                    disabled={!targetRecords.length}
                    onClick={() => {
                      const ris = buildRisExport(targetRecords);
                      downloadTextFile(
                        `${slugBase}-citations.ris`,
                        ris,
                        "application/x-research-info-systems;charset=utf-8",
                      );
                      setStatusNote({ tone: "good", text: t("handoffFileDownloaded") });
                    }}
                  >
                    <RisEndnoteIcon size={14} />
                    <span>{t("handoffDownloadRis")}</span>
                  </button>
                  <button
                    type="button"
                    className="button secondary small"
                    disabled={!targetRecords.length}
                    onClick={() => {
                      const csl = buildCslJsonExport(targetRecords, exportKeyMap);
                      downloadTextFile(
                        `${slugBase}-csl.json`,
                        csl,
                        "application/json;charset=utf-8",
                      );
                      setStatusNote({ tone: "good", text: t("handoffFileDownloaded") });
                    }}
                  >
                    <CslJsonIcon size={14} />
                    <span>{t("handoffDownloadCsl")}</span>
                  </button>
                  <button
                    type="button"
                    className="button secondary small"
                    disabled={!targetRecords.length}
                    onClick={() =>
                      void copyText(buildBibtexExport(targetRecords, exportKeyMap), t("handoffCopiedFile"))
                    }
                  >
                    {t("handoffCopyBib")}
                  </button>
                  <button
                    type="button"
                    className="button secondary small"
                    disabled={!targetRecords.length}
                    onClick={() =>
                      void copyText(buildApaBibliography(targetRecords), t("handoffCopiedFile"))
                    }
                  >
                    {t("handoffCopyApa")}
                  </button>
                </div>
              </article>

              {(onCopyMasterMarkdown || onExportMasterCsv) && (
                <article className="handoff-export-card">
                  <div>
                    <h3>{t("handoffExportTableTitle")}</h3>
                    <p className="small muted">{t("handoffExportTableDesc")}</p>
                  </div>
                  <div className="handoff-export-actions">
                    {onCopyMasterMarkdown && (
                      <button
                        type="button"
                        className="button secondary small"
                        disabled={!targetRecords.length}
                        onClick={() => {
                          void onCopyMasterMarkdown(targetRecords).then((ok) => {
                            setStatusNote({
                              tone: ok ? "good" : "bad",
                              text: ok ? t("catalogTableCopied") : t("handoffCopyFailed"),
                            });
                          });
                        }}
                      >
                        {t("catalogTableCopyMd")}
                      </button>
                    )}
                    {onExportMasterCsv && (
                      <button
                        type="button"
                        className="button secondary small"
                        disabled={!targetRecords.length}
                        onClick={() => {
                          onExportMasterCsv(targetRecords);
                          setStatusNote({ tone: "good", text: t("handoffFileDownloaded") });
                        }}
                      >
                        {t("catalogTableExportCsv")}
                      </button>
                    )}
                  </div>
                </article>
              )}
            </div>
          )}

          {statusNote && (
            <p
              role="status"
              className={`handoff-status-note ${statusNote.tone === "good" ? "good-text" : "bad-text"}`}
            >
              {statusNote.tone === "good" ? "✓ " : ""}
              {statusNote.text}
            </p>
          )}
        </div>
      </section>
    </div>,
    document.body,
  );
}
