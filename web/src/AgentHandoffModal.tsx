import { useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { safeSourceUrl } from "./api";
import { ErrorMessage } from "./components";
import type { Translate } from "./i18n";
import type { IntegrationLiveState, ResearchRecord, Workspace } from "./types";

export type HandoffPresetId =
  | "zotero-obsidian"
  | "notebooklm-brief"
  | "seven-section-summary"
  | "triage-gap";

export type HandoffScope = "selected" | "filtered";
export type HandoffTab = "agent" | "export";

export interface HandoffTaskResult {
  id: string;
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

function collectTags(record: ResearchRecord): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of [...strings(record.data.tags), ...strings(record.data.labels)]) {
    const cleaned = raw.trim().replace(/^#+/, "");
    if (!cleaned) continue;
    const key = cleaned.toLocaleLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      out.push(cleaned);
    }
  }
  return out;
}

function rawScope(record: ResearchRecord): string {
  return (text(record.data.reading_level) || text(record.data.reading_scope) || "unknown").trim();
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
  const cleaned = value.replace(/\r?\n/g, " ").trim();
  return JSON.stringify(cleaned);
}

function bibtexEscape(value: string): string {
  return value.replace(/\r?\n/g, " ").replace(/[{}]/g, "").trim();
}

function makeCiteKey(record: ResearchRecord, index: number): string {
  const authors = collectAuthors(record.data.authors);
  const firstAuthor = authors[0] || "source";
  const surname = firstAuthor
    .split(/[\s,]+/)
    .filter(Boolean)
    .pop()
    ?.toLowerCase()
    .replace(/[^a-z0-9]/g, "") || "source";
  const year = text(record.data.year).replace(/[^0-9]/g, "").slice(0, 4) || "nd";
  const titleWord =
    text(record.data.title)
      .toLowerCase()
      .split(/[^a-z0-9]+/)
      .find((w) => w.length >= 4 && !["with", "from", "that", "this", "into", "over"].includes(w)) ||
    `item${index + 1}`;
  return `${surname}${year}${titleWord}`;
}

export function buildObsidianMarkdown(
  records: ResearchRecord[],
  screenings: Map<string, "include" | "exclude" | null>,
  projectTitle?: string,
): string {
  if (records.length === 1) {
    const record = records[0];
    const authors = collectAuthors(record.data.authors);
    const tags = collectTags(record);
    const cat = categorySlug(record);
    const doi = text(record.data.doi).trim();
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
    const relevance = text(record.data.relevance).trim();

    const frontmatter = [
      "---",
      `title: ${yamlQuote(text(record.data.title))}`,
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
      `# ${text(record.data.title)}`,
      "",
      `> Reading scope: \`${scope}\` · Screening: \`${decision}\` · Identity: \`${identity}\``,
      "",
      "## Summary",
      summary || "_No summary recorded yet._",
      "",
      "## Relevance",
      relevance || "_No relevance note recorded yet._",
    ];
    return `${frontmatter}\n\n${sections.join("\n")}\n`;
  }

  const allTags = [...new Set(records.flatMap(collectTags))];
  const frontmatter = [
    "---",
    `title: ${yamlQuote(`${projectTitle || "Research Hub"} — Literature Export (${records.length})`)}`,
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
    const relevance = text(record.data.relevance).trim();
    return [
      `## ${index + 1}. ${text(record.data.title)} (${year})`,
      `- **Authors**: ${authors || "—"}`,
      `- **Category**: \`${cat}\` · **Reading scope**: \`${scope}\` · **Screening**: \`${decision}\``,
      tags.length ? `- **Tags**: ${tags.map((tag) => `#${tag.replace(/\s+/g, "-")}`).join(" ")}` : null,
      doi ? `- **DOI**: \`${doi}\`` : null,
      url ? `- **Source**: ${url}` : null,
      summary ? `\n${summary}` : null,
      relevance ? `\n**Relevance**: ${relevance}` : null,
    ]
      .filter(Boolean)
      .join("\n");
  });

  return `${frontmatter}\n\n# ${projectTitle || "Research Hub"} — Literature Bundle (${records.length})\n\n${blocks.join("\n\n---\n\n")}\n`;
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
    const relevance = text(record.data.relevance).trim();
    return [
      `### ${index + 1}. ${text(record.data.title)} (${year})`,
      `- Authors: ${authors || "Unknown"}`,
      `- Reading Scope: ${scope}`,
      `- Category: ${categorySlug(record) || "unclassified"}`,
      tags.length ? `- Keywords/Labels: ${tags.join(", ")}` : null,
      doi ? `- DOI: ${doi}` : null,
      summary ? `\n${summary}` : "\n[No abstract or summary saved locally.]",
      relevance ? `\nRelevance note: ${relevance}` : null,
    ]
      .filter(Boolean)
      .join("\n");
  };

  return [
    `# NotebookLM Source Pack: ${projectTitle || "Research Hub Literature"}`,
    "",
    "> **Evidence-Boundary Notice for NotebookLM**:",
    `> - Full-text declared sources: ${fullText.length}`,
    `> - Abstract / metadata-only / unknown-scope sources: ${abstractOrPartial.length}`,
    "> - Do NOT attribute detailed experimental methods, sample sizes, or p-values to abstract-only or metadata-only items unless verified in full text.",
    "",
    "## CLI Bundle & Upload Commands",
    "```bash",
    `research-hub notebooklm bundle ${slug}`,
    `research-hub notebooklm upload ${slug} --dry-run`,
    `# After inspecting dry-run output:`,
    `research-hub notebooklm upload ${slug} --create-if-missing`,
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

export function buildBibtexExport(records: ResearchRecord[]): string {
  const usedKeys = new Set<string>();
  return (
    records
      .map((record, index) => {
        let key = makeCiteKey(record, index);
        if (usedKeys.has(key)) {
          key = `${key}_${index + 1}`;
        }
        usedKeys.add(key);
        const authors = collectAuthors(record.data.authors).join(" and ");
        const venue = text(record.data.venue).trim() || text(record.data.journal).trim();
        const year = text(record.data.year).trim();
        const doi = text(record.data.doi).trim();
        const url =
          record.data.locator_kind !== "local-copy"
            ? safeSourceUrl(record.data.locator) || ""
            : "";
        const tags = [...new Set([categorySlug(record), ...collectTags(record)].filter(Boolean))];
        const summary = savedSummary(record);
        const scope = rawScope(record);
        const identity = text(record.data.identity_status).trim() || "unverified";
        const fields: [string, string][] = [
          ["title", bibtexEscape(text(record.data.title))],
          authors ? ["author", bibtexEscape(authors)] : ["", ""],
          year ? ["year", bibtexEscape(year)] : ["", ""],
          venue ? ["journal", bibtexEscape(venue)] : ["", ""],
          doi ? ["doi", bibtexEscape(doi)] : ["", ""],
          url ? ["url", bibtexEscape(url)] : ["", ""],
          tags.length ? ["keywords", bibtexEscape(tags.join(", "))] : ["", ""],
          summary ? ["abstract", bibtexEscape(summary)] : ["", ""],
          ["note", `Reading scope: ${scope}; Identity: ${identity}`],
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
}: {
  preset: HandoffPresetId;
  records: ResearchRecord[];
  screenings: Map<string, "include" | "exclude" | null>;
  projectId?: string;
  projectTitle?: string;
  locale: "en" | "zh-TW";
}): { operation: "synthesize" | "frame"; prompt: string } {
  const pid = projectId || "<project-id>";
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
      `${index + 1}. "${text(record.data.title)}" (${year})`,
      `source_id=${record.id}`,
      `category=${cat}`,
      `reading_scope=${scope}`,
      `screening=${decision}`,
      tags.length ? `labels=[${tags.join(", ")}]` : null,
      doi ? `doi=${doi}` : null,
      url ? `url=${url}` : null,
    ].filter(Boolean);
    return parts.join(" | ");
  });

  const isZh = locale === "zh-TW";
  const header = isZh
    ? [
        `# Research Hub AI 助理交接指令`,
        `- 專案：${projectTitle || pid} (\`${pid}\`)`,
        `- 目標文獻：${records.length} 篇（全文宣告：${fullTextCount}，僅摘要／書目／未知：${abstractCount}）`,
        "",
      ]
    : [
        `# Research Hub AI Agent Handoff`,
        `- Project: ${projectTitle || pid} (\`${pid}\`)`,
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
          "2. 產出標準 ingest JSON，**先執行 dry-run 預覽**：",
          `   \`research-hub ingest <papers.json> --cluster ${pid} --dry-run\``,
          "3. 將 dry-run 差異（新增／略過／標籤／分類）回報給我確認；**獲得明確核准後**才執行正式寫入 Zotero 與 Obsidian Vault。",
          "4. 同步完成後，可協助執行 `scripts/library_snapshot.py` 更新 Research Hub 唯讀快照。",
        ]
      : [
          "## Task: Convert & Sync to Zotero + Obsidian",
          "1. Verify DOI / bibliographic identity for the sources below while preserving `category`, `labels`, and `reading_scope` (NEVER promote `abstract` or `metadata` items to `full-text`).",
          "2. Build an ingest payload and run a **dry-run preview first**:",
          `   \`research-hub ingest <papers.json> --cluster ${pid} --dry-run\``,
          "3. Report the dry-run diff (adds / skips / categories / labels) and **wait for my explicit approval** before writing to Zotero or Obsidian.",
          "4. After approval and ingest, refresh the read-only UI snapshot via `scripts/library_snapshot.py`.",
        ];
  } else if (preset === "notebooklm-brief") {
    instructions = isZh
      ? [
          "## 任務目標：打包送進 NotebookLM 並驗證簡報",
          "1. 針對下列文獻先檢查哪些已有全文 PDF、哪些僅有摘要（Abstract only）。對僅摘要文獻明確標示證據邊界，不可將摘要推論當作全文方法。",
          "2. 依序執行打包與乾跑預覽：",
          `   \`research-hub notebooklm bundle ${pid}\``,
          `   \`research-hub notebooklm upload ${pid} --dry-run\``,
          "3. 確認清單與 NotebookLM 登入狀態（`research-hub notebooklm status`）無誤，經我確認後再上傳並產生簡報，最後用 `notebooklm-brief-verifier` 核對每條引用。",
        ]
      : [
          "## Task: Prepare NotebookLM Bundle & Verify Brief",
          "1. Separate full-text PDF sources from abstract-only / metadata-only sources below and explicitly mark evidence boundaries.",
          "2. Bundle and preview upload first (never upload without showing dry-run output):",
          `   \`research-hub notebooklm bundle ${pid}\``,
          `   \`research-hub notebooklm upload ${pid} --dry-run\``,
          "3. Check `research-hub notebooklm status`; after my approval, upload, generate the brief, and verify every claim with `notebooklm-brief-verifier`.",
        ];
  } else if (preset === "seven-section-summary") {
    instructions = isZh
      ? [
          "## 任務目標：精讀並產出 7 段結構化摘要（paper-summarize）",
          "1. 依據每篇文獻的實際可讀範圍（`reading_scope`）使用 `paper-summarize` 產出 7 段結構化摘要（研究緣由／目的／方法／發現／結論／重點／限制），並附上原文引句與 `supported` / `inference` / `unknown` 標記。",
          "2. 若文獻僅為 `abstract` 或 `metadata`，未提及的方法／限制必須誠實標記為 `unknown`，不可腦補。",
          `3. 產出 JSON 後，透過 \`research-hub project native-summary-import --project ${pid} --source-id <source_id> --file <summary.json>\` 匯入 Research Hub 供我人工審閱。`,
        ]
      : [
          "## Task: Generate 7-Section Structured Summaries (`paper-summarize`)",
          "1. Using each paper's true `reading_scope`, run `paper-summarize` to draft a 7-section structured summary with verbatim evidence quotes and `supported` / `inference` / `unknown` labels.",
          "2. For `abstract` or `metadata` items, mark unstated methods/limitations honestly as `unknown`—never invent full-text claims.",
          `3. Import the draft for human review via \`research-hub project native-summary-import --project ${pid} --source-id <source_id> --file <summary.json>\`.`,
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
  return {
    operation,
    prompt: [...header, ...instructions, "", listHeading, ...paperLines].join("\n"),
  };
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
  URL.revokeObjectURL(url);
}

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
  t: Translate;
  onClose: () => void;
  onCreateHandoffTask?: (payload: {
    operation: "synthesize" | "frame";
    instructions: string;
  }) => Promise<HandoffTaskResult>;
  onNavigateReview?: (taskId?: string) => void;
  onOpenSetup?: () => void;
  onCopyMasterMarkdown?: () => Promise<void>;
  onExportMasterCsv?: () => void;
}) {
  const dialogId = useId();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [tab, setTab] = useState<HandoffTab>("agent");
  const [scope, setScope] = useState<HandoffScope>(initialScope);
  const [preset, setPreset] = useState<HandoffPresetId>("zotero-obsidian");
  const [customPrompt, setCustomPrompt] = useState<string | null>(null);
  const [statusNote, setStatusNote] = useState<{ tone: "good" | "bad"; text: string } | null>(null);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<unknown>(null);
  const [createdTaskId, setCreatedTaskId] = useState<string | null>(null);

  const locale: "en" | "zh-TW" =
    t("catalogTitle") === "文獻目錄" ? "zh-TW" : "en";

  useEffect(() => {
    if (!open) return;
    setScope(initialScope === "selected" && selectedRecord ? "selected" : "filtered");
    setCustomPrompt(null);
    setStatusNote(null);
    setCreateError(null);
    setCreatedTaskId(null);
    requestAnimationFrame(() => headingRef.current?.focus());
  }, [open, initialScope, selectedRecord]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  const targetRecords = useMemo(() => {
    if (scope === "selected" && selectedRecord) return [selectedRecord];
    return filteredRecords;
  }, [scope, selectedRecord, filteredRecords]);

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

  const effectivePrompt = customPrompt ?? generated.prompt;
  const fullTextCount = targetRecords.filter((r) => rawScope(r) === "full-text").length;
  const abstractOnlyCount = targetRecords.length - fullTextCount;

  if (!open) return null;

  const obsidianOk =
    liveIntegrations?.obsidian?.status === "valid" ||
    workspace?.capabilities?.obsidian_validation?.status === "available";
  const zoteroOk = liveIntegrations?.zotero
    ? ["connected_local_and_web", "connected_web", "connected_local"].includes(
        liveIntegrations.zotero.status,
      )
    : Boolean(
        (liveIntegrations?.credentials ?? workspace?.capabilities?.local_integrations)
          ?.zotero_configured,
      );
  const nlmOk = liveIntegrations?.notebooklm
    ? liveIntegrations.notebooklm.status === "authenticated"
    : Boolean(
        (liveIntegrations?.credentials ?? workspace?.capabilities?.local_integrations)
          ?.nlm_state_present,
      );

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
    if (!onCreateHandoffTask || creating || !targetRecords.length) return;
    setCreating(true);
    setCreateError(null);
    setStatusNote(null);
    try {
      const created = await onCreateHandoffTask({
        operation: generated.operation,
        instructions: effectivePrompt,
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

  return createPortal(
    <div
      className="handoff-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
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
          <div className="handoff-dest-bar" aria-label={t("handoffPipelineReadiness")}>
            <span className={`pipeline-dot-chip ${obsidianOk ? "is-ok" : "is-idle"}`}>Obsidian</span>
            <span className={`pipeline-dot-chip ${zoteroOk ? "is-ok" : "is-idle"}`}>Zotero</span>
            <span className={`pipeline-dot-chip ${nlmOk ? "is-ok" : "is-idle"}`}>NotebookLM</span>
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
                    disabled={creating || !targetRecords.length}
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
          ) : (
            <div className="handoff-export-grid">
              <article className="handoff-export-card">
                <div>
                  <h3>{t("handoffExportObsidianTitle")}</h3>
                  <p className="small muted">{t("handoffExportObsidianDesc")}</p>
                </div>
                <div className="handoff-export-actions">
                  <button
                    type="button"
                    className="button primary small"
                    disabled={!targetRecords.length}
                    onClick={() => {
                      const md = buildObsidianMarkdown(targetRecords, screenings, projectTitle);
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
                    onClick={() =>
                      void copyText(
                        buildObsidianMarkdown(targetRecords, screenings, projectTitle),
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
                  <h3>{t("handoffExportNlmTitle")}</h3>
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
                  <h3>{t("handoffExportZoteroTitle")}</h3>
                  <p className="small muted">{t("handoffExportZoteroDesc")}</p>
                </div>
                <div className="handoff-export-actions">
                  <button
                    type="button"
                    className="button primary small"
                    disabled={!targetRecords.length}
                    onClick={() => {
                      const bib = buildBibtexExport(targetRecords);
                      downloadTextFile(
                        `${slugBase}-zotero.bib`,
                        bib,
                        "application/x-bibtex;charset=utf-8",
                      );
                      setStatusNote({ tone: "good", text: t("handoffFileDownloaded") });
                    }}
                  >
                    {t("handoffDownloadBib")}
                  </button>
                  <button
                    type="button"
                    className="button secondary small"
                    disabled={!targetRecords.length}
                    onClick={() =>
                      void copyText(buildBibtexExport(targetRecords), t("handoffCopiedFile"))
                    }
                  >
                    {t("handoffCopyBib")}
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
                        disabled={!filteredRecords.length}
                        onClick={() => void onCopyMasterMarkdown()}
                      >
                        {t("catalogTableCopyMd")}
                      </button>
                    )}
                    {onExportMasterCsv && (
                      <button
                        type="button"
                        className="button secondary small"
                        disabled={!filteredRecords.length}
                        onClick={() => {
                          onExportMasterCsv();
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
