import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  buildAgentHandoffPrompt,
  buildBibtexExport,
  buildNotebookLmSourcePack,
  buildObsidianMarkdown,
  computeDestinationStatuses,
  MAX_HANDOFF_TASK_CHARS,
} from "./AgentHandoffModal";
import { LiteratureLibrary } from "./LiteratureLibrary";
import { translator } from "./i18n";
import type { IntegrationLiveState, ResearchRecord, Workspace } from "./types";

const tEn = translator("en");
const tZh = translator("zh-TW");

const sampleSources: ResearchRecord[] = [
  {
    id: "src-full-1",
    kind: "source",
    data: {
      title: "Generative Agents: Interactive Simulacra of Human Behavior",
      authors: ["Joon Sung Park", "Joseph C. O'Brien", "Michael S. Bernstein"],
      year: "2023",
      venue: "UIST 2023",
      category: "llm-agents",
      tags: ["multi-agent", "simulation", "memory"],
      reading_scope: "full-text",
      doi: "10.1145/3586183.3606763",
      locator: "https://doi.org/10.1145/3586183.3606763",
      summary: "Introduces memory-stream architectures for believable interactive agents.",
      working_summary: {
        text: "Reviewed working note: memory reflection drives emergent planning.",
        artifact_id: "art-work-1",
        artifact_sha256: "a".repeat(64),
        source_revision: "b".repeat(64),
        previous_revision: "c".repeat(64),
        saved_at: "2026-11-26T00:00:00Z",
      },
      relevance: "Core baseline for multi-agent social simulation.",
      identity_status: "unverified",
    },
  },
  {
    id: "src-abs-2",
    kind: "source",
    data: {
      title: "Out of One, Many: Using Language Models to Simulate Human Samples",
      authors: ["Lisa P. Argyle", "Ethan C. Busby"],
      year: "2023",
      venue: "Political Analysis",
      category: "human-simulation",
      tags: ["silicon-sampling", "bias", "multi-agent"],
      reading_scope: "abstract",
      doi: "10.1017/pan.2023.2",
      locator: "https://doi.org/10.1017/pan.2023.2",
      abstract: "Demonstrates algorithmic fidelity across demographic subgroups.",
      identity_status: "unverified",
    },
  },
  {
    id: "src-meta-3",
    kind: "source",
    data: {
      title: "Hydrological Agent-Based Water Allocation Benchmark",
      authors: ["Lin Wei"],
      year: "2024",
      category: "water-abm",
      tags: ["hydrology", "benchmark"],
      reading_scope: "metadata",
      locator: "https://example.org/hydro-abm",
      identity_status: "unverified",
    },
  },
];

describe("semantic labels, tag curation, and AI agent handoff exports", () => {
  it("filters literature by reading-scope labels and keyword tag labels, and clears all filters together", async () => {
    const user = userEvent.setup();
    render(
      <LiteratureLibrary
        sources={sampleSources}
        screenings={[]}
        t={tEn}
        onScreen={vi.fn()}
        onPrepare={vi.fn()}
      />,
    );

    const scopeGroup = screen.getByRole("group", { name: tEn("catalogFilterByScope") });
    await user.click(within(scopeGroup).getByRole("button", { name: /Abstract only/i }));
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(1);
    expect(screen.getByRole("heading", { name: /Out of One, Many/ })).toBeVisible();

    await user.click(screen.getByRole("button", { name: tEn("catalogClearFilters") }));
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(3);

    const tagGroup = screen.getByRole("group", { name: tEn("catalogFilterByTag") });
    await user.click(within(tagGroup).getByRole("button", { name: /#multi-agent/i }));
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(2);

    await user.click(within(tagGroup).getByRole("button", { name: /#multi-agent/i }));
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(3);
  });

  it("edits keyword labels with Chinese/English commas in Category & details and emits deduplicated tags", async () => {
    const user = userEvent.setup();
    const onCurate = vi.fn().mockResolvedValue(undefined);
    render(
      <LiteratureLibrary
        sources={sampleSources}
        screenings={[]}
        curations={[]}
        t={tEn}
        onScreen={vi.fn()}
        onCurate={onCurate}
        onPrepare={vi.fn()}
      />,
    );

    await user.click(screen.getByText(tEn("catalogEditMeta")));
    const form = screen.getByRole("button", { name: tEn("catalogSaveMeta") }).closest("form")!;
    const tagsInput = within(form).getByLabelText(tEn("catalogMetaTags"));
    expect(tagsInput).toHaveValue("multi-agent, simulation, memory");

    await user.clear(tagsInput);
    await user.type(tagsInput, "#multi-agent， social-sim; evaluation, Multi-Agent");
    await user.click(within(form).getByRole("button", { name: tEn("catalogSaveMeta") }));

    expect(onCurate).toHaveBeenCalledWith("src-full-1", {
      tags: ["multi-agent", "social-sim", "evaluation"],
    });
  });

  it("opens AI Agent Handoff modal, emits real CLI contracts, preserves state across parent refresh, and binds selected_source_ids", async () => {
    const user = userEvent.setup();
    let triggerRerender!: () => void;
    const onCreateHandoffTask = vi.fn().mockImplementation(async () => {
      // Simulate App.tsx calling setDetail(fresh) with freshly cloned source objects while modal stays open
      triggerRerender();
      return { id: "task-handoff-42" };
    });
    const onNavigateReview = vi.fn();

    const makeProps = (sources: ResearchRecord[]) => ({
      sources,
      screenings: [] as ResearchRecord[],
      projectId: "demo-20",
      projectTitle: "20-Paper Benchmark Review",
      locale: "en" as const,
      t: tEn,
      onScreen: vi.fn(),
      onPrepare: vi.fn(),
      onCreateHandoffTask,
      onNavigateReview,
    });

    const { rerender } = render(<LiteratureLibrary {...makeProps(sampleSources)} />);
    triggerRerender = () => {
      rerender(<LiteratureLibrary {...makeProps(structuredClone(sampleSources))} />);
    };

    await user.click(screen.getByRole("button", { name: tEn("handoffOpenButton") }));
    const dialog = screen.getByRole("dialog", { name: tEn("handoffModalTitle") });
    expect(dialog).toBeVisible();

    const promptBox = within(dialog).getByLabelText(tEn("handoffPromptLabel")) as HTMLTextAreaElement;
    expect(promptBox.value).toContain("research-hub ingest --input <papers.json> --cluster demo-20 --dry-run");
    expect(promptBox.value).toContain("reading_scope=abstract");
    expect(promptBox.value).toContain("labels=[multi-agent, simulation, memory]");

    // Switch to NotebookLM preset & verify --cluster flag + cluster creation + research-hub doctor (no nonexistent status subcommand)
    await user.click(within(dialog).getByRole("button", { name: new RegExp(tEn("handoffPresetNlmTitle")) }));
    expect(promptBox.value).toContain("research-hub clusters new --query");
    expect(promptBox.value).toContain("research-hub notebooklm bundle --cluster demo-20");
    expect(promptBox.value).toContain("research-hub notebooklm upload --cluster demo-20 --dry-run");
    expect(promptBox.value).toContain("research-hub doctor");
    expect(promptBox.value).not.toContain("notebooklm status");

    // Switch to 7-Section summary preset & verify --root / --project / --path CLI flags
    await user.click(within(dialog).getByRole("button", { name: new RegExp(tEn("handoffPresetSummaryTitle")) }));
    expect(promptBox.value).toContain("research-hub project native-summary-import --root <workspace-root> --project demo-20 --path");

    // Switch scope to Selected paper (1), edit prompt, create task (which triggers parent refresh!)
    await user.click(within(dialog).getByRole("button", { name: `${tEn("handoffScopeSelected")} (1)` }));
    await user.type(promptBox, "\nExtra human instruction.");
    await user.click(within(dialog).getByRole("button", { name: tEn("handoffCreateTask") }));

    expect(onCreateHandoffTask).toHaveBeenCalledWith(
      expect.objectContaining({
        operation: "synthesize",
        selected_source_ids: ["src-full-1"],
        instructions: expect.stringContaining("Extra human instruction."),
      }),
    );

    // Even after parent rerendered with fresh source objects, status note, edited prompt, and Review link MUST persist!
    expect(promptBox.value).toContain("Extra human instruction.");
    const openReview = await within(dialog).findByRole("button", {
      name: new RegExp(tEn("handoffOpenInReview")),
    });
    expect(openReview).toBeVisible();
    await user.click(openReview);
    expect(onNavigateReview).toHaveBeenCalledWith("task-handoff-42");
  });

  it("renders Traditional Chinese prompts inside the modal when locale is zh-TW and closes modal on pageSuspended", async () => {
    const user = userEvent.setup();
    const props = {
      sources: sampleSources,
      screenings: [] as ResearchRecord[],
      projectId: "water-abm",
      projectTitle: "水資源綜述",
      locale: "zh-TW" as const,
      t: tZh,
      onScreen: vi.fn(),
      onPrepare: vi.fn(),
    };
    const { rerender } = render(<LiteratureLibrary {...props} pageSuspended={false} />);
    await user.click(screen.getByRole("button", { name: tZh("handoffOpenButton") }));
    const dialog = screen.getByRole("dialog", { name: tZh("handoffModalTitle") });
    const promptBox = within(dialog).getByLabelText(tZh("handoffPromptLabel")) as HTMLTextAreaElement;
    expect(promptBox.value).toContain("Research Hub AI 助理交接指令");
    expect(promptBox.value).toContain("水資源綜述");
    expect(promptBox.value).toContain("research-hub ingest --input <papers.json> --cluster water-abm --dry-run");

    // Navigating away (pageSuspended=true) must close the portaled modal cleanly
    rerender(<LiteratureLibrary {...props} pageSuspended={true} />);
    expect(screen.queryByRole("dialog", { name: tZh("handoffModalTitle") })).toBeNull();
  });

  it("narrows Markdown table export inside the modal when Selected paper scope is active", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });

    render(
      <LiteratureLibrary
        sources={sampleSources}
        screenings={[]}
        t={tEn}
        onScreen={vi.fn()}
        onPrepare={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("button", { name: tEn("handoffOpenPaperButton") }));
    const dialog = screen.getByRole("dialog", { name: tEn("handoffModalTitle") });
    await user.click(within(dialog).getByRole("tab", { name: tEn("handoffTabExport") }));
    await user.click(within(dialog).getByRole("button", { name: tEn("catalogTableCopyMd") }));

    expect(writeText).toHaveBeenCalledTimes(1);
    const copied = writeText.mock.calls[0][0] as string;
    expect(copied).toContain("Generative Agents");
    expect(copied).not.toContain("Out of One, Many");
    expect(copied).not.toContain("Hydrological Agent-Based");
  });

  it("bounds 120-paper auto handoff task instructions to <= 20,000 chars, escapes BibTeX/YAML safely, exports working_summary, and lets failed probes override capability", () => {
    const screenings = new Map<string, "include" | "exclude" | null>([
      ["src-full-1", "include"],
      ["src-abs-2", null],
      ["src-meta-3", "exclude"],
    ]);

    // Working summary appears in Obsidian & NotebookLM exports
    const singleMd = buildObsidianMarkdown([sampleSources[0]], screenings, "Demo");
    expect(singleMd).toContain('reading_scope: "full-text"');
    expect(singleMd).toContain('tags: ["multi-agent", "simulation", "memory"]');
    expect(singleMd).toContain("## Working Summary (Unverified Draft)");
    expect(singleMd).toContain("memory reflection drives emergent planning");

    const nlmPack = buildNotebookLmSourcePack(sampleSources, "Study $(printf evil) $HOME 'x'", "demo-20");
    expect(nlmPack).toContain("Full-Text Declared Sources (1)");
    expect(nlmPack).toContain("Abstract-Only & Metadata Sources (2)");
    expect(nlmPack).toContain("research-hub clusters new --query 'Study $(printf evil) $HOME '\\''x'\\''' --slug demo-20");
    expect(nlmPack).toContain("research-hub notebooklm bundle --cluster demo-20");
    expect(nlmPack).toContain("#### Working Summary (Unverified Draft)");

    // BibTeX & YAML escaping with hostile characters + CSL "Smith, John" surname extraction
    const tricky: ResearchRecord = {
      id: "src-tricky",
      kind: "source",
      data: {
        title: "95% Accuracy & {Braces} with Trailing\\\u2028Line",
        authors: [{ family: "Smith", given: "John" }],
        year: "2024",
        doi: "10.1000/test_doi",
        locator: "https://example.org/paper%20v1",
        tags: ["AI_Agents", "ai_agents", "50%"],
        reading_scope: "abstract}\n@evil{x",
        abstract: "Achieves 95% gain & $10 cost with #1 rank and trailing \\",
        identity_status: "unverified",
      },
    };
    const bib = buildBibtexExport([tricky]);
    expect(bib).toContain("@article{smith2024accuracy,");
    expect(bib).toContain("95\\% Accuracy \\& \\{Braces\\}");
    expect(bib).toContain("\\textbackslash{}");
    expect(bib).toContain("url = {https://example.org/paper%20v1}");
    expect(bib).toContain("Reading scope: abstract\\} @evil\\{x; Identity: unverified");

    const trickyMd = buildObsidianMarkdown([tricky], new Map(), "Demo");
    expect(trickyMd).not.toContain("\u2028");

    // 120-paper bounded handoff prompt fits <= 20,000 chars
    const bigCohort: ResearchRecord[] = Array.from({ length: 120 }, (_, i) => ({
      id: `src-big-${i + 1}`,
      kind: "source",
      data: {
        title: `Large-Scale Multi-Agent Empirical Evaluation Study Number ${i + 1} Across Hydrological and Economic Benchmarks`,
        year: "2024",
        category: "llm-agents",
        tags: ["multi-agent", "benchmark", "validation", "hydrology"],
        reading_scope: i % 2 === 0 ? "full-text" : "abstract",
        doi: `10.1000/big.2024.${String(i + 1).padStart(4, "0")}`,
        locator: `https://doi.org/10.1000/big.2024.${String(i + 1).padStart(4, "0")}`,
      },
    }));
    const bounded = buildAgentHandoffPrompt({
      preset: "zotero-obsidian",
      records: bigCohort,
      screenings: new Map(),
      projectId: "big-120",
      projectTitle: "Big 120 Cohort",
      locale: "en",
      maxChars: MAX_HANDOFF_TASK_CHARS,
    });
    expect(bounded.prompt.length).toBeLessThanOrEqual(MAX_HANDOFF_TASK_CHARS);
    expect(bounded.truncatedCount).toBeGreaterThan(0);

    // Failed live Obsidian probe MUST override startup capability availability ("error", not "ok")
    const ws = {
      capabilities: {
        obsidian_validation: { version: 1, status: "available", read_only: true, scope: "startup_selected_exact_vault" },
        local_integrations: { version: 1, status: "available", zotero_configured: true, nlm_state_present: true },
      },
    } as unknown as Workspace;
    expect(computeDestinationStatuses(ws, {})).toEqual({
      obsidian: "configured",
      zotero: "configured",
      notebooklm: "configured",
    });
    const failedLive: IntegrationLiveState = {
      obsidian: { ok: false, status: "not_found", code: "not_found", observed_at: "2026-11-26T00:00:00Z" } as unknown as IntegrationLiveState["obsidian"],
      zotero: { status: "auth_failed", local_api: false, web_api: "auth_failed", observed_at: "2026-11-26T00:00:00Z" },
      notebooklm: { status: "expired", code: "auth_invalid", refreshed: false, state_present: true, observed_at: "2026-11-26T00:00:00Z" },
    };
    expect(computeDestinationStatuses(ws, failedLive)).toEqual({
      obsidian: "error",
      zotero: "error",
      notebooklm: "error",
    });
  });
});
