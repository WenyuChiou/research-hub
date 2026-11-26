import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  buildAgentHandoffPrompt,
  buildBibtexExport,
  buildNotebookLmSourcePack,
  buildObsidianMarkdown,
} from "./AgentHandoffModal";
import { LiteratureLibrary } from "./LiteratureLibrary";
import { translator } from "./i18n";
import type { ResearchRecord } from "./types";

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

  it("edits keyword labels in Category & details and emits tags in append-only curation payload", async () => {
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
    await user.type(tagsInput, "#multi-agent, social-sim, evaluation");
    await user.click(within(form).getByRole("button", { name: tEn("catalogSaveMeta") }));

    expect(onCurate).toHaveBeenCalledWith("src-full-1", {
      tags: ["multi-agent", "social-sim", "evaluation"],
    });
  });

  it("opens AI Agent Handoff modal, switches presets, creates tracked handoff task, and navigates to review", async () => {
    const user = userEvent.setup();
    const onCreateHandoffTask = vi.fn().mockResolvedValue({ id: "task-handoff-42" });
    const onNavigateReview = vi.fn();

    render(
      <LiteratureLibrary
        sources={sampleSources}
        screenings={[]}
        projectId="demo-20"
        projectTitle="20-Paper Benchmark Review"
        t={tEn}
        onScreen={vi.fn()}
        onPrepare={vi.fn()}
        onCreateHandoffTask={onCreateHandoffTask}
        onNavigateReview={onNavigateReview}
      />,
    );

    await user.click(screen.getByRole("button", { name: tEn("handoffOpenButton") }));
    const dialog = screen.getByRole("dialog", { name: tEn("handoffModalTitle") });
    expect(dialog).toBeVisible();

    const promptBox = within(dialog).getByLabelText(tEn("handoffPromptLabel"));
    expect((promptBox as HTMLTextAreaElement).value).toContain("research-hub ingest");
    expect((promptBox as HTMLTextAreaElement).value).toContain("reading_scope=abstract");
    expect((promptBox as HTMLTextAreaElement).value).toContain("labels=[multi-agent, simulation, memory]");

    await user.click(within(dialog).getByRole("button", { name: new RegExp(tEn("handoffPresetNlmTitle")) }));
    expect((promptBox as HTMLTextAreaElement).value).toContain("research-hub notebooklm bundle demo-20");

    await user.click(within(dialog).getByRole("button", { name: tEn("handoffCreateTask") }));
    expect(onCreateHandoffTask).toHaveBeenCalledWith(
      expect.objectContaining({
        operation: "synthesize",
        instructions: expect.stringContaining("notebooklm bundle demo-20"),
      }),
    );

    const openReview = await within(dialog).findByRole("button", {
      name: new RegExp(tEn("handoffOpenInReview")),
    });
    await user.click(openReview);
    expect(onNavigateReview).toHaveBeenCalledWith("task-handoff-42");
  });

  it("generates honest Obsidian Markdown, NotebookLM Source Pack, Zotero BibTeX, and zh-TW agent prompts", () => {
    const screenings = new Map<string, "include" | "exclude" | null>([
      ["src-full-1", "include"],
      ["src-abs-2", null],
      ["src-meta-3", "exclude"],
    ]);

    const singleMd = buildObsidianMarkdown([sampleSources[0]], screenings, "Demo");
    expect(singleMd).toContain('reading_scope: "full-text"');
    expect(singleMd).toContain('tags: ["multi-agent", "simulation", "memory"]');
    expect(singleMd).toContain('screening: "include"');

    const bundleMd = buildObsidianMarkdown(sampleSources, screenings, "Demo");
    expect(bundleMd).toContain("paper_count: 3");
    expect(bundleMd).toContain("#silicon-sampling");

    const nlmPack = buildNotebookLmSourcePack(sampleSources, "Demo", "demo-20");
    expect(nlmPack).toContain("Full-Text Declared Sources (1)");
    expect(nlmPack).toContain("Abstract-Only & Metadata Sources (2)");
    expect(nlmPack).toContain("research-hub notebooklm bundle demo-20");

    const bib = buildBibtexExport(sampleSources);
    expect(bib).toContain("@article{");
    expect(bib).toContain("doi = {10.1145/3586183.3606763}");
    expect(bib).toContain("keywords = {llm-agents, multi-agent, simulation, memory}");
    expect(bib).toContain("Reading scope: abstract; Identity: unverified");

    const zhPrompt = buildAgentHandoffPrompt({
      preset: "triage-gap",
      records: sampleSources,
      screenings,
      projectId: "demo-20",
      projectTitle: "水資源多代理人綜述",
      locale: "zh-TW",
    });
    expect(zhPrompt.operation).toBe("frame");
    expect(zhPrompt.prompt).toContain("literature-triage-matrix");
    expect(zhPrompt.prompt).toContain("水資源多代理人綜述");
    expect(tZh("handoffOpenButton")).toBe("AI 助理與匯出");
  });
});
