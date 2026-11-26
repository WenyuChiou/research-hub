import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { applySourceCurations, buildLiteratureSummaryStats, LiteratureLibrary } from "./LiteratureLibrary";
import { translator } from "./i18n";
import input from "./test-fixtures/catalog-synthetic20.json";
import type { ResearchRecord } from "./types";

const sources: ResearchRecord[] = input.map((paper) => ({
  id: paper.id, kind: "source",
  data: {...paper, locator:paper.url, identity_status:"unverified", human_acceptance:"pending"},
}));
const t = translator("en");

describe("literature collection", () => {
  it("browses the saved20, combines category and keyword filters, and preserves source coverage", async () => {
    const user = userEvent.setup();
    render(<LiteratureLibrary sources={sources} screenings={[]} t={t} onScreen={vi.fn()} onPrepare={vi.fn()} />);
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(20);
    expect(screen.getByText(t("catalogNoSummary"))).toBeVisible();
    await user.selectOptions(screen.getByLabelText(t("catalogCategory")), "llm");
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(8);
    await user.type(screen.getByLabelText(t("catalogSearch")), "opinions");
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(1);
    expect(screen.getByRole("heading", {name:"Synthetic model opinions comparator"})).toBeVisible();
    expect(screen.getByRole("link", {name:t("catalogOriginalSource")})).toHaveAttribute("href", "https://example.org/synthetic-library/18");
    expect(screen.getAllByText(t("catalogAbstractSnippet")).length).toBeGreaterThan(0);
    await user.clear(screen.getByLabelText(t("catalogSearch")));
    await user.type(screen.getByLabelText(t("catalogSearch")), "no matching title");
    expect(screen.getByText(t("catalogNoMatches"))).toBeVisible();
    expect(screen.queryByRole("heading", {name:"Synthetic model opinions comparator"})).not.toBeInTheDocument();
  });

  it("matches coauthors when searching papers displayed as FirstAuthor et al.", async () => {
    const user = userEvent.setup();
    const multiAuthor: ResearchRecord = {
      id: "multi-author-paper",
      kind: "source",
      data: {
        title: "Accurate Sum and Dot Product",
        authors: ["Takeshi Ogita", "Siegfried M. Rump", "Shin'ichi Oishi"],
        year: 2005,
        identity_status: "unverified",
        human_acceptance: "pending",
      },
    };
    render(<LiteratureLibrary sources={[multiAuthor]} screenings={[]} t={t} onScreen={vi.fn()} onPrepare={vi.fn()} />);
    expect(screen.getAllByText("Takeshi Ogita et al.").length).toBeGreaterThan(0);
    await user.type(screen.getByLabelText(t("catalogSearch")), "Rump");
    expect(screen.getByRole("button", { name: "Accurate Sum and Dot Product" })).toBeVisible();
  });

  it("binds a screening note to the selected source and reads its saved decision without promoting reading status", async () => {
    const user = userEvent.setup();
    const save = vi.fn().mockResolvedValue(undefined);
    const props = {sources, screenings:[] as ResearchRecord[], t, onScreen:save, onPrepare:vi.fn()};
    const {rerender} = render(<LiteratureLibrary {...props} />);
    const title = "Synthetic brand choice comparator";
    await user.click(screen.getByRole("button", {name:title}));
    await user.click(screen.getByText(t("catalogScreening")));
    await user.selectOptions(screen.getByRole("combobox", {name:new RegExp(t("decision"))}), "include");
    await user.type(screen.getByRole("textbox", {name:new RegExp(t("rationale"))}), "Keep as an abstract-level brand-choice comparator.");
    await user.click(screen.getByRole("button", {name:t("catalogSaveScreening")}));
    expect(save).toHaveBeenCalledWith("synthetic-04", "include", "Keep as an abstract-level brand-choice comparator.");
    rerender(<LiteratureLibrary {...props} screenings={[{id:"saved-decision",kind:"screening",data:{source_id:"synthetic-04",decision:"include",rationale:"Keep as an abstract-level brand-choice comparator."}}]} />);
    expect(screen.getByText("Keep as an abstract-level brand-choice comparator.")).toBeVisible();
    expect(screen.getByText(t("catalogNoSummary"))).toBeVisible();
    expect(sources[3].data.identity_status).toBe("unverified");
    expect(sources[3].data.human_acceptance).toBe("pending");
  });
});

const organizationSources: ResearchRecord[] = [
  {id:"sort-a", kind:"source", data:{title:"Unsorted local paper", category:"  ", summary:"  ", relevance:"A relevance note is not a summary.", reading_level:"abstract", identity_status:"unverified", human_acceptance:"pending"}},
  {id:"sort-b", kind:"source", data:{title:"Saved abstract paper", category:"human", summary:"  ", abstract:"An existing saved abstract.", reading_level:"abstract", identity_status:"unverified", human_acceptance:"pending"}},
  {id:"obsidian:1234567890abcdef12345678", kind:"library-note", data:{title:"Existing readonly note", category:"notes", summary:"\n\t", abstract:"An existing note abstract.", reading_level:"note-metadata", read_only:true}},
  {id:"sort-d", kind:"source", data:{title:"Model source awaiting a decision", category:"llm", summary:0, reading_level:"abstract-snippet", identity_status:"unverified", human_acceptance:"pending"}},
];
const organizationScreenings: ResearchRecord[] = [
  {id:"screen-b", kind:"screening", data:{source_id:"sort-b", decision:"include", rationale:"An explicitly saved screening reason."}},
  {id:"screen-d-old", kind:"screening", data:{source_id:"sort-d", decision:"include", rationale:"An older screening reason."}},
  {id:"screen-d-latest", kind:"screening", data:{source_id:"sort-d", decision:"unknown", rationale:"A current unresolved decision."}},
];
const organizationProps = (tr = t) => ({sources:organizationSources, screenings:organizationScreenings, t:tr, onScreen:vi.fn(), onPrepare:vi.fn()});

describe("organizing saved material", () => {
  it("shows overlapping collection counts and limits pending screening to Workspace sources", async () => {
    const user = userEvent.setup();
    render(<LiteratureLibrary {...organizationProps()} />);
    const filters = within(screen.getByRole("group", {name:t("catalogOrganize")}));
    expect(filters.getByRole("button", {name:`${t("catalogAllMaterial")} (4)`})).toHaveAttribute("aria-pressed", "true");
    expect(filters.getByRole("button", {name:`${t("catalogNeedsCategory")} (1)`})).toBeVisible();
    expect(filters.getByRole("button", {name:`${t("catalogNeedsSummary")} (2)`})).toBeVisible();
    await user.click(filters.getByRole("button", {name:`${t("catalogNeedsScreening")} (2)`}));
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(2);
    expect(screen.queryByRole("button", {name:"Existing readonly note"})).not.toBeInTheDocument();
    expect(screen.queryByRole("button", {name:"Saved abstract paper"})).not.toBeInTheDocument();
  });

  it("combines organization, category and search, and clears them together without writes or network calls", async () => {
    const user = userEvent.setup();
    const callbacks = organizationProps();
    const fetch = vi.spyOn(globalThis, "fetch");
    render(<LiteratureLibrary {...callbacks} />);
    await user.click(screen.getByRole("button", {name:`${t("catalogNeedsSummary")} (2)`}));
    await user.selectOptions(screen.getByLabelText(t("catalogCategory")), "llm");
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(1);
    expect(screen.getByRole("heading", {name:"Model source awaiting a decision"})).toBeVisible();
    await user.type(screen.getByLabelText(t("catalogSearch")), "not a saved title");
    expect(screen.getByText(t("catalogNoMatches"))).toBeVisible();
    await user.click(screen.getByRole("button", {name:t("catalogClearFilters")}));
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(4);
    expect(screen.getByLabelText(t("catalogSearch"))).toHaveValue("");
    expect(screen.getByLabelText(t("catalogCategory"))).toHaveValue("");
    expect(callbacks.onScreen).not.toHaveBeenCalled();
    expect(callbacks.onPrepare).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("uses actual saved text for summary presence and never promotes relevance, numeric values, or reading scope", async () => {
    const user = userEvent.setup();
    const original = JSON.stringify(organizationSources);
    render(<LiteratureLibrary {...organizationProps()} />);
    await user.click(screen.getByRole("button", {name:`${t("catalogNeedsSummary")} (2)`}));
    expect(screen.getByText(t("catalogNoSummary"))).toBeVisible();
    expect(screen.queryByRole("button", {name:"Saved abstract paper"})).not.toBeInTheDocument();
    expect(screen.queryByRole("button", {name:"Existing readonly note"})).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", {name:"Model source awaiting a decision"}));
    expect(screen.getAllByText(t("catalogAbstractSnippet")).length).toBeGreaterThan(0);
    expect(JSON.stringify(organizationSources)).toBe(original);
  });

  it("updates the pending list when a valid screening is read back without changing human reading or identity", async () => {
    const user = userEvent.setup();
    const props = organizationProps();
    const {rerender} = render(<LiteratureLibrary {...props} />);
    await user.click(screen.getByRole("button", {name:`${t("catalogNeedsScreening")} (2)`}));
    await user.click(screen.getByRole("button", {name:"Model source awaiting a decision"}));
    rerender(<LiteratureLibrary {...props} screenings={[...organizationScreenings,
      {id:"screen-d-new",kind:"screening",data:{source_id:"sort-d",decision:"exclude",rationale:"A newly saved exclusion reason."}},
    ]} />);
    expect(screen.getByRole("button", {name:`${t("catalogNeedsScreening")} (1)`})).toHaveAttribute("aria-pressed", "true");
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(1);
    expect(screen.getByRole("heading", {name:"Unsorted local paper"})).toBeVisible();
    expect(organizationSources[3].data.identity_status).toBe("unverified");
    expect(organizationSources[3].data.human_acceptance).toBe("pending");
  });

  it("keeps a source pending when a saved decision lacks a textual reason", () => {
    render(<LiteratureLibrary {...organizationProps()} sources={[organizationSources[0]]}
      screenings={[{id:"malformed-reason",kind:"screening",data:{source_id:"sort-a",decision:"include",rationale:123}}]} />);
    expect(screen.getByRole("button", {name:`${t("catalogNeedsScreening")} (1)`})).toBeVisible();
  });

  it.each(["en", "zh-TW"] as const)("supports keyboard filtering and reset in %s", async (locale) => {
    const user = userEvent.setup();
    const tr = translator(locale);
    render(<LiteratureLibrary {...organizationProps(tr)} />);
    expect(screen.getByRole("combobox", {name:tr("catalogCategory")})).toBeVisible();
    expect(screen.getByRole("combobox", {name:tr("catalogCategory")})).toHaveAttribute("aria-label", tr("catalogCategory"));
    expect(screen.getByRole("searchbox", {name:tr("catalogSearch")})).toBeVisible();
    screen.getByRole("button", {name:`${tr("catalogNeedsCategory")} (1)`}).focus();
    await user.keyboard("{Enter}");
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(1);
    screen.getByRole("button", {name:tr("catalogClearFilters")}).focus();
    await user.keyboard("{Enter}");
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(4);
    expect(screen.getByRole("searchbox", {name:tr("catalogSearch")})).toHaveFocus();
  });
});

describe("opening selected material", () => {
  it.each(["en", "zh-TW"] as const)("moves keyboard focus to the details and returns to the same row in %s", async (locale) => {
    const user = userEvent.setup();
    const tr = translator(locale);
    render(<LiteratureLibrary {...organizationProps(tr)} />);
    const row = screen.getByRole("button", {name:"Model source awaiting a decision"});
    row.focus();
    await user.keyboard("{Enter}");
    const heading = screen.getByRole("heading", {name:"Model source awaiting a decision"});
    expect(heading).toHaveFocus();
    expect(row).toHaveAttribute("aria-controls", heading.closest("aside")?.id);
    await user.click(screen.getByRole("button", {name:tr("catalogBackToList")}));
    expect(row).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(heading).toHaveFocus();
  });

  it("shows existing summary, source, coverage and saved screening without implying provider transfer is available", async () => {
    const user = userEvent.setup();
    const callbacks = organizationProps();
    const source = {...organizationSources[1],data:{...organizationSources[1].data,locator:"https://example.org/selected-source"}};
    const original = JSON.stringify(source);
    render(<LiteratureLibrary {...callbacks} sources={[source]} />);
    const details = within(screen.getByRole("complementary", {name:t("catalogDetail")}));
    expect(details.getByText("An existing saved abstract.")).toBeVisible();
    expect(details.getByRole("link", {name:t("catalogOriginalSource")})).toHaveAttribute("href", "https://example.org/selected-source");
    expect(details.getByText(t("catalogAbstractOnly"))).toBeVisible();
    expect(details.getByRole("region", {name:t("catalogOrganizationState")})).toHaveTextContent(t("catalogScreeningRecorded"));
    await user.click(details.getByText(t("catalogToolUse")));
    expect(details.getByText(t("catalogZoteroUnavailable"))).toBeVisible();
    expect(details.getByText(t("catalogObsidianUnavailable"))).toBeVisible();
    expect(details.getByText(t("catalogNlmUnavailable"))).toBeVisible();
    expect(details.queryByRole("button", {name:/zotero|notebooklm|obsidian/i})).not.toBeInTheDocument();
    await user.click(details.getByRole("button", {name:t("catalogSourceTools")}));
    expect(callbacks.onPrepare).toHaveBeenCalledWith(source);
    expect(callbacks.onScreen).not.toHaveBeenCalled();
    expect(JSON.stringify(source)).toBe(original);
  });

  it("makes missing organization work explicit for a selected item without treating relevance as its summary", async () => {
    const user = userEvent.setup();
    render(<LiteratureLibrary {...organizationProps()} sources={[organizationSources[0]]} />);
    await user.click(screen.getByRole("button", {name:"Unsorted local paper"}));
    const state = within(screen.getByRole("region", {name:t("catalogOrganizationState")}));
    expect(state.getByText(t("catalogNeedsCategory"))).toBeVisible();
    expect(state.getByText(t("catalogNeedsSummary"))).toBeVisible();
    expect(state.getByText(t("catalogNeedsScreening"))).toBeVisible();
    expect(screen.getByText(t("catalogNoSummary"))).toBeVisible();
    expect(screen.getByText("A relevance note is not a summary.")).toBeVisible();
  });

  it("keeps note snapshots read-only and does not steal filter focus on a normal data refresh", async () => {
    const user = userEvent.setup();
    const props = organizationProps();
    const {rerender} = render(<LiteratureLibrary {...props} />);
    await user.click(screen.getByRole("button", {name:"Existing readonly note"}));
    const details = within(screen.getByRole("complementary", {name:t("catalogDetail")}));
    expect(details.getByText(t("catalogReadOnlyItem"))).toBeVisible();
    expect(details.queryByRole("button", {name:t("catalogSourceTools")})).not.toBeInTheDocument();
    await user.click(details.getByText(t("catalogToolUse")));
    expect(details.getByText(t("catalogObsidianReadOnly"))).toBeVisible();
    const search = screen.getByLabelText(t("catalogSearch"));
    await user.type(search, "Existing");
    rerender(<LiteratureLibrary {...props} sources={[...organizationSources]} />);
    expect(search).toHaveFocus();
    expect(props.onScreen).not.toHaveBeenCalled();
    expect(props.onPrepare).not.toHaveBeenCalled();
  });

  it("surfaces live failed Obsidian validation instead of claiming configured ready", async () => {
    const user = userEvent.setup();
    render(
      <LiteratureLibrary
        {...organizationProps()}
        sources={[organizationSources[0]]}
        workspace={{
          ok: true,
          projects: [],
          protection_scope: "synthetic",
          capabilities: {
            codex: { status: "unavailable", message: "" },
            writing: { status: "unavailable", message: "" },
            approval: { status: "unavailable", message: "" },
            obsidian_validation: { version: 1, status: "available", read_only: true, scope: "startup_selected_exact_vault" },
          },
        }}
        liveIntegrations={{ obsidian: { status: "registry_mismatch", observed_at: "2026-11-25T00:00:00Z" } }}
      />,
    );
    const details = within(screen.getByRole("complementary", { name: t("catalogDetail") }));
    await user.click(details.getByText(t("catalogToolUse")));
    expect(details.getByText(t("obsidianRegistryMismatch"))).toBeVisible();
    expect(details.queryByText(t("catalogObsidianConfigured"))).not.toBeInTheDocument();
  });

  it("does not render a stray 0 when source authors/venue are empty and identity matches map has an empty array", () => {
    const bareSource = {
      ...organizationSources[0],
      id: "bare-src",
      data: { title: "Bare Paper Title", reading_scope: "abstract" },
    };
    const { container } = render(
      <LiteratureLibrary
        {...organizationProps()}
        sources={[bareSource]}
        matches={new Map([["bare-src", []]])}
      />,
    );
    const titleCell = container.querySelector("tbody td:first-child")!;
    expect(titleCell.querySelector(".catalog-submeta")).toBeNull();
    expect(titleCell.textContent).toBe("Bare Paper Title");
  });
});

describe("master literature table, category summary, and clean status tooltips", () => {
  it("switches to master table, filters by category cards, sorts by year, copies Markdown, and jumps back to reader", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    const tableSources: ResearchRecord[] = [
      { id: "src-old-id", kind: "source", data: { title: "Older Human Study | Pipe", category: "human", year: 2019, authors: ["Alice Lin"], reading_level: "abstract", summary: "Saved summary.", locator: "https://example.org/human-2019", identity_status: "unverified" } },
      { id: "src-new-id", kind: "source", data: { title: "Newer LLM Study", category: "llm", year: 2025, authors: ["Bob Chen", "Carol Wu", "Dan Li"], reading_level: "full-text", locator: "https://example.org/llm-2025", identity_status: "unverified" } },
      { id: "src-unclass-id", kind: "source", data: { title: "Unclassified Note", category: "", year: 2022, reading_level: "metadata", locator: "javascript:alert(1)", identity_status: "unverified" } },
    ];
    const tableScreenings: ResearchRecord[] = [
      { id: "scr-1", kind: "screening", data: { source_id: "src-old-id", decision: "include", rationale: "Relevant comparator." } },
    ];
    render(<LiteratureLibrary sources={tableSources} screenings={tableScreenings} t={t} onScreen={vi.fn()} onPrepare={vi.fn()} />);

    // Unverified badge carries plain-language tooltip in split desk
    expect(screen.getByText(t("unverified"))).toHaveAttribute("data-tooltip", t("unverifiedTip"));

    // Switch to Master Table view
    await user.click(screen.getByRole("button", { name: t("catalogViewTable") }));
    const categoryStrip = screen.getByRole("group", { name: t("catalogTableCategorySummary") });
    expect(within(categoryStrip).getByRole("button", { name: new RegExp(t("catalogAllCategories")) })).toHaveAttribute("aria-pressed", "true");
    expect(within(categoryStrip).getByRole("button", { name: new RegExp(t("catalogLlm")) })).toBeVisible();
    expect(within(categoryStrip).getByRole("button", { name: new RegExp(t("catalogUnclassified")) })).toBeVisible();

    // Unsafe javascript: locator is never rendered as an anchor
    const masterTable = screen.getByRole("table");
    expect(within(masterTable).getAllByRole("link")).toHaveLength(2);
    expect(masterTable.textContent).not.toContain("src-old-id");

    // Sort by Year descending then ascending
    const yearSort = within(masterTable).getByRole("button", { name: new RegExp(t("catalogYear")) });
    await user.click(yearSort);
    let rows = within(masterTable).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("Newer LLM Study");
    expect(rows[2]).toHaveTextContent("Older Human Study | Pipe");
    await user.click(yearSort);
    rows = within(masterTable).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("Older Human Study | Pipe");
    expect(rows[2]).toHaveTextContent("Newer LLM Study");

    // Copy Markdown table escapes pipes and excludes raw record IDs
    await user.click(screen.getByRole("button", { name: t("catalogTableCopyMd") }));
    expect(writeText).toHaveBeenCalledTimes(1);
    const md = writeText.mock.calls[0][0] as string;
    expect(md).toContain("Older Human Study \\| Pipe");
    expect(md).toContain("https://example.org/llm-2025");
    expect(md).not.toContain("javascript:alert");
    expect(md).not.toContain("src-old-id");

    // Filter by category card
    await user.click(within(categoryStrip).getByRole("button", { name: new RegExp(t("catalogLlm")) }));
    expect(within(screen.getByRole("table")).getAllByRole("row").slice(1)).toHaveLength(1);

    // Click paper title to jump into Split Desk reading that exact paper
    await user.click(screen.getByRole("button", { name: "Newer LLM Study" }));
    expect(screen.getByRole("heading", { name: "Newer LLM Study" })).toHaveFocus();

    // Switching back to Master Table and clicking the ALREADY-selected paper still restores heading focus
    await user.click(screen.getByRole("button", { name: t("catalogViewTable") }));
    await user.click(screen.getByRole("button", { name: "Newer LLM Study" }));
    expect(screen.getByRole("heading", { name: "Newer LLM Study" })).toHaveFocus();
  });

  it("places records without numeric years at the bottom in both descending and ascending year sorts", async () => {
    const user = userEvent.setup();
    const yearSources: ResearchRecord[] = [
      { id: "no-year-1", kind: "source", data: { title: "Undated First", category: "human", identity_status: "unverified" } },
      { id: "yr-2021", kind: "source", data: { title: "Dated 2021", category: "human", year: 2021, identity_status: "unverified" } },
      { id: "no-year-2", kind: "source", data: { title: "Undated Second", category: "llm", year: "n/a", identity_status: "unverified" } },
      { id: "yr-2024", kind: "source", data: { title: "Dated 2024", category: "llm", year: 2024, identity_status: "unverified" } },
    ];
    render(<LiteratureLibrary sources={yearSources} screenings={[]} t={t} onScreen={vi.fn()} onPrepare={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: t("catalogViewTable") }));
    const yearSort = within(screen.getByRole("table")).getByRole("button", { name: new RegExp(t("catalogYear")) });
    await user.click(yearSort);
    let rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("Dated 2024");
    expect(rows[1]).toHaveTextContent("Dated 2021");
    expect(rows[2]).toHaveTextContent("Undated First");
    expect(rows[3]).toHaveTextContent("Undated Second");
    await user.click(yearSort);
    rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("Dated 2021");
    expect(rows[1]).toHaveTextContent("Dated 2024");
    expect(rows[2]).toHaveTextContent("Undated First");
    expect(rows[3]).toHaveTextContent("Undated Second");
  });

  it("summarizes literature categories cleanly and avoids raw source ID labels in both locales", () => {
    const stats = buildLiteratureSummaryStats(organizationSources, organizationScreenings);
    expect(stats.total).toBe(4);
    expect(stats.categorized).toBe(3);
    expect(stats.included).toBe(1);
    expect(stats.awaiting).toBe(2);
    expect(stats.groups.at(-1)?.isUnclassified).toBe(true);

    const zh = translator("zh-TW");
    expect(t("sourceIds")).toBe("Supporting sources");
    expect(zh("sourceIds")).toBe("支持文獻");
    expect(zh("sourceId")).toBe("對應文獻");
  });

  it("clears prior search query when an overview category request arrives", async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <LiteratureLibrary sources={sources} screenings={[]} t={t} onScreen={vi.fn()} onPrepare={vi.fn()} />,
    );
    await user.type(screen.getByLabelText(t("catalogSearch")), "opinions");
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(1);
    rerender(
      <LiteratureLibrary
        sources={sources}
        screenings={[]}
        t={t}
        onScreen={vi.fn()}
        onPrepare={vi.fn()}
        requestedView={{ mode: "table", category: "human", nonce: 1 }}
      />,
    );
    expect(screen.getByLabelText(t("catalogSearch"))).toHaveValue("");
    expect(within(screen.getByRole("table")).getAllByRole("row").slice(1).length).toBeGreaterThan(1);
  });

  it("preserves unsaved working-summary edits while toggling to master table and back to reader", async () => {
    const user = userEvent.setup();
    const sha = "a".repeat(64);
    const artifact = {
      id: "art-1",
      project_id: "proj-1",
      source_record_id: "src-1",
      role: "evidence",
      path: "reports/draft.md",
      sha256: sha,
      current: true,
    };
    const record: ResearchRecord = {
      id: "src-1",
      kind: "source",
      data: {
        id: "src-1",
        title: "Editable Summary Paper",
        category: "llm",
        identity_status: "unverified",
        source_records: [
          {
            observation_id: "obs-1",
            work_id: "work-1",
            source_id: "src-1",
            evidence_level: "generated-summary",
            status: "available",
            text_path: "reports/draft.md",
            text_sha256: sha,
          },
        ],
      },
    };
    vi.spyOn(globalThis, "fetch").mockImplementation(async (inputUrl) => {
      const url = String(inputUrl);
      if (url.includes("/working-summary")) {
        return new Response(
          JSON.stringify({
            ok: true,
            context: {
              source_record_id: "src-1",
              artifact_id: "art-1",
              artifact_sha256: sha,
              revision: "b".repeat(64),
              draft_text: "Initial draft text.",
              working_summary: null,
            },
          }),
          { headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(
        JSON.stringify({
          ok: true,
          preview: {
            artifact_id: "art-1",
            sha256: sha,
            path: "reports/draft.md",
            text: "Initial draft text.",
          },
        }),
        { headers: { "Content-Type": "application/json" } },
      );
    });
    render(
      <LiteratureLibrary
        sources={[record]}
        screenings={[]}
        t={t}
        onScreen={vi.fn()}
        onPrepare={vi.fn()}
        observationRead={{ projectId: "proj-1", artifacts: [artifact], active: true, revision: 0 }}
      />,
    );
    await user.click(screen.getByRole("button", { name: `${t("workingSummaryReview")} art-1` }));
    const editor = await screen.findByRole("textbox", { name: t("workingSummaryText") });
    await user.type(editor, " Unsaved human edit.");
    expect(editor).toHaveValue("Initial draft text. Unsaved human edit.");

    await user.click(screen.getByRole("button", { name: t("catalogViewTable") }));
    expect(screen.getByRole("table")).toBeVisible();
    await user.click(screen.getByRole("button", { name: t("catalogViewSplit") }));
    expect(screen.getByRole("textbox", { name: t("workingSummaryText") })).toHaveValue(
      "Initial draft text. Unsaved human edit.",
    );
  });

  it("preserves unsaved working-summary edits even when overview opens a different category", async () => {
    const user = userEvent.setup();
    const sha = "c".repeat(64);
    const artifact = {
      id: "art-cat",
      project_id: "proj-cat",
      source_record_id: "src-llm",
      role: "evidence",
      path: "reports/llm.md",
      sha256: sha,
      current: true,
    };
    const llmRecord: ResearchRecord = {
      id: "src-llm",
      kind: "source",
      data: {
        id: "src-llm",
        title: "LLM Paper Being Edited",
        category: "llm",
        identity_status: "unverified",
        source_records: [
          {
            observation_id: "obs-llm",
            work_id: "work-llm",
            source_id: "src-llm",
            evidence_level: "generated-summary",
            status: "available",
            text_path: "reports/llm.md",
            text_sha256: sha,
          },
        ],
      },
    };
    const humanRecord: ResearchRecord = {
      id: "src-human",
      kind: "source",
      data: {
        id: "src-human",
        title: "Human Study In Other Category",
        category: "human",
        identity_status: "unverified",
      },
    };
    vi.spyOn(globalThis, "fetch").mockImplementation(async (inputUrl) => {
      const url = String(inputUrl);
      if (url.includes("/working-summary")) {
        return new Response(
          JSON.stringify({
            ok: true,
            context: {
              source_record_id: "src-llm",
              artifact_id: "art-cat",
              artifact_sha256: sha,
              revision: "d".repeat(64),
              draft_text: "LLM draft.",
              working_summary: null,
            },
          }),
          { headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(
        JSON.stringify({
          ok: true,
          preview: { artifact_id: "art-cat", sha256: sha, path: "reports/llm.md", text: "LLM draft." },
        }),
        { headers: { "Content-Type": "application/json" } },
      );
    });
    const base = {
      sources: [llmRecord, humanRecord],
      screenings: [],
      t,
      onScreen: vi.fn(),
      onPrepare: vi.fn(),
      observationRead: { projectId: "proj-cat", artifacts: [artifact], active: true, revision: 0 },
    };
    const { rerender } = render(<LiteratureLibrary {...base} requestedView={{ mode: "split", nonce: 0 }} />);
    await user.click(screen.getByRole("button", { name: `${t("workingSummaryReview")} art-cat` }));
    const editor = await screen.findByRole("textbox", { name: t("workingSummaryText") });
    await user.type(editor, " Unsaved cross-category edit.");

    // Overview jumps to a DIFFERENT category ("human") that excludes src-llm from visible
    rerender(<LiteratureLibrary {...base} requestedView={{ mode: "table", category: "human", nonce: 1 }} />);
    expect(within(screen.getByRole("table")).getAllByRole("row").slice(1)).toHaveLength(1);
    expect(within(screen.getByRole("table")).getByText("Human Study In Other Category")).toBeVisible();

    // Clicking the human paper in Master Table honors the selection immediately AND exposes a safe return to the unsaved draft
    await user.click(screen.getByRole("button", { name: "Human Study In Other Category" }));
    expect(screen.getByRole("heading", { name: "Human Study In Other Category" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: `${t("catalogReturnDraft")}: LLM Paper Being Edited` }));
    expect(screen.getByRole("textbox", { name: t("workingSummaryText") })).toHaveValue(
      "LLM draft. Unsaved cross-category edit.",
    );

    // Clicking another paper in the split list still switches cleanly without destroying the draft
    await user.click(screen.getByRole("button", { name: "Human Study In Other Category" }));
    expect(screen.getByRole("heading", { name: "Human Study In Other Category" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "LLM Paper Being Edited" }));
    expect(screen.getByRole("textbox", { name: t("workingSummaryText") })).toHaveValue(
      "LLM draft. Unsaved cross-category edit.",
    );

    // Closing the working summary removes the unsaved-draft banner
    await user.click(screen.getByRole("button", { name: t("cancel") }));
    await user.click(screen.getByRole("button", { name: "Human Study In Other Category" }));
    expect(screen.queryByRole("button", { name: new RegExp(t("catalogReturnDraft")) })).not.toBeInTheDocument();
  });

  it("retains unsaved working-summary edits on compact viewports when overview opens another category and user returns to Reader", async () => {
    vi.stubGlobal("matchMedia", () => ({
      matches: true,
      media: "(max-width: 1080px)",
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    vi.stubGlobal("scrollTo", vi.fn());
    const user = userEvent.setup();
    const sha = "e".repeat(64);
    const artifact = {
      id: "art-compact",
      project_id: "proj-compact",
      source_record_id: "src-llm-c",
      role: "evidence",
      path: "reports/compact.md",
      sha256: sha,
      current: true,
    };
    const llmRecord: ResearchRecord = {
      id: "src-llm-c",
      kind: "source",
      data: {
        id: "src-llm-c",
        title: "Compact LLM Draft",
        category: "llm",
        identity_status: "unverified",
        source_records: [
          {
            observation_id: "obs-c",
            work_id: "work-c",
            source_id: "src-llm-c",
            evidence_level: "generated-summary",
            status: "available",
            text_path: "reports/compact.md",
            text_sha256: sha,
          },
        ],
      },
    };
    const humanRecord: ResearchRecord = {
      id: "src-human-c",
      kind: "source",
      data: { id: "src-human-c", title: "Compact Human Paper", category: "human", identity_status: "unverified" },
    };
    vi.spyOn(globalThis, "fetch").mockImplementation(async (inputUrl) => {
      const url = String(inputUrl);
      if (url.includes("/working-summary")) {
        return new Response(
          JSON.stringify({
            ok: true,
            context: {
              source_record_id: "src-llm-c",
              artifact_id: "art-compact",
              artifact_sha256: sha,
              revision: "f".repeat(64),
              draft_text: "Compact base.",
              working_summary: null,
            },
          }),
          { headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(
        JSON.stringify({
          ok: true,
          preview: { artifact_id: "art-compact", sha256: sha, path: "reports/compact.md", text: "Compact base." },
        }),
        { headers: { "Content-Type": "application/json" } },
      );
    });
    try {
      const base = {
        sources: [llmRecord, humanRecord],
        screenings: [],
        t,
        onScreen: vi.fn(),
        onPrepare: vi.fn(),
        observationRead: { projectId: "proj-compact", artifacts: [artifact], active: true, revision: 0 },
      };
      const { rerender } = render(<LiteratureLibrary {...base} requestedView={{ mode: "split", nonce: 0 }} />);
      await user.click(screen.getByRole("button", { name: "Compact LLM Draft" }));
      await user.click(screen.getByRole("button", { name: `${t("workingSummaryReview")} art-compact` }));
      const editor = await screen.findByRole("textbox", { name: t("workingSummaryText") });
      await user.type(editor, " Unsaved compact text.");

      // Overview jumps to a different category ("human"), then user clicks Reader (not a paper row)
      rerender(<LiteratureLibrary {...base} requestedView={{ mode: "table", category: "human", nonce: 1 }} />);
      await user.click(screen.getByRole("button", { name: t("catalogViewSplit") }));

      // Return-to-draft banner is accessible right from compact list and restores exact unsaved text
      await user.click(screen.getByRole("button", { name: `${t("catalogReturnDraft")}: Compact LLM Draft` }));
      expect(screen.getByRole("textbox", { name: t("workingSummaryText") })).toHaveValue(
        "Compact base. Unsaved compact text.",
      );
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("curates category, year, authors, venue, relevance, and summary without mutating source identity", async () => {
    const user = userEvent.setup();
    const onCurate = vi.fn().mockResolvedValue(undefined);
    const bare: ResearchRecord = {
      id: "src-curate-1",
      kind: "source",
      data: {
        title: "ReAct: Synergizing Reasoning and Acting",
        locator: "https://arxiv.org/abs/2210.03629",
        identity_status: "unverified",
        human_acceptance: "pending",
      },
    };
    const originalSnapshot = JSON.stringify(bare);
    const { rerender } = render(
      <LiteratureLibrary
        sources={[bare]}
        screenings={[]}
        curations={[]}
        t={t}
        onScreen={vi.fn()}
        onCurate={onCurate}
        onPrepare={vi.fn()}
      />,
    );
    await user.click(screen.getByText(t("catalogEditMeta")));
    const form = screen.getByRole("button", { name: t("catalogSaveMeta") }).closest("form")!;
    await user.type(within(form).getByLabelText(t("catalogCategory")), "llm");
    await user.type(within(form).getByLabelText(t("catalogYear")), "2023");
    await user.type(within(form).getByLabelText(t("catalogMetaAuthors")), "Shunyu Yao, Jeffrey Zhao");
    await user.type(within(form).getByLabelText(t("catalogMetaVenue")), "ICLR 2023");
    await user.type(within(form).getByLabelText(t("catalogRelevance")), "Core agent reasoning baseline.");
    await user.type(within(form).getByLabelText(t("catalogMetaSummary")), "Interleaves thought and action traces.");
    await user.click(within(form).getByRole("button", { name: t("catalogSaveMeta") }));

    expect(onCurate).toHaveBeenCalledWith("src-curate-1", {
      category: "llm",
      year: "2023",
      authors: ["Shunyu Yao", "Jeffrey Zhao"],
      venue: "ICLR 2023",
      relevance: "Core agent reasoning baseline.",
      summary: "Interleaves thought and action traces.",
    });

    const curations: ResearchRecord[] = [
      {
        id: "cur-1",
        kind: "source_curation",
        data: {
          source_id: "src-curate-1",
          category: "llm",
          year: "2023",
          authors: ["Shunyu Yao", "Jeffrey Zhao"],
          venue: "ICLR 2023",
          relevance: "Core agent reasoning baseline.",
          summary: "Interleaves thought and action traces.",
        },
      },
    ];
    rerender(
      <LiteratureLibrary
        sources={[bare]}
        screenings={[]}
        curations={curations}
        t={t}
        onScreen={vi.fn()}
        onCurate={onCurate}
        onPrepare={vi.fn()}
      />,
    );
    expect(screen.getAllByText("Shunyu Yao, Jeffrey Zhao · ICLR 2023").length).toBeGreaterThan(0);
    expect(screen.getByText("Interleaves thought and action traces.", { selector: "p.preserve-lines" })).toBeVisible();
    expect(within(form).getByRole("status")).toHaveTextContent(t("saved"));
    expect(JSON.stringify(bare)).toBe(originalSnapshot);
    expect(applySourceCurations([bare], curations)[0].data.identity_status).toBe("unverified");
  });

  it("preserves unsaved curation notes across collapsing the editor and switching papers", async () => {
    const user = userEvent.setup();
    const first: ResearchRecord = {
      id: "src-draft-a",
      kind: "source",
      data: { title: "First Paper", locator: "https://example.org/a", year: "2024" },
    };
    const second: ResearchRecord = {
      id: "src-draft-b",
      kind: "source",
      data: { title: "Second Paper", locator: "https://example.org/b", year: "2025" },
    };
    render(
      <LiteratureLibrary
        sources={[first, second]}
        screenings={[]}
        curations={[]}
        t={t}
        onScreen={vi.fn()}
        onCurate={vi.fn().mockResolvedValue(undefined)}
        onPrepare={vi.fn()}
      />,
    );
    await user.click(screen.getByText(t("catalogEditMeta")));
    const form = screen.getByRole("button", { name: t("catalogSaveMeta") }).closest("form")!;
    await user.type(within(form).getByLabelText(t("catalogRelevance")), "Work-in-progress relevance note");

    // Collapse the details panel and re-open: unsaved text and indicator must remain.
    await user.click(screen.getByText(t("catalogEditMeta")));
    expect(screen.getByText(t("catalogMetaUnsaved"))).toBeVisible();
    await user.click(screen.getByText(t("catalogEditMeta")));
    expect(screen.getByLabelText(t("catalogRelevance"))).toHaveValue("Work-in-progress relevance note");

    // Switch to second paper and return to first paper: unsaved text must remain intact.
    await user.click(screen.getByRole("button", { name: "Second Paper" }));
    expect(screen.getByLabelText(t("catalogRelevance"))).toHaveValue("");
    await user.click(screen.getByRole("button", { name: "First Paper" }));
    expect(screen.getByLabelText(t("catalogRelevance"))).toHaveValue("Work-in-progress relevance note");

    // Explicit Discard clears the unsaved draft.
    await user.click(screen.getByRole("button", { name: t("catalogResetMeta") }));
    expect(screen.getByLabelText(t("catalogRelevance"))).toHaveValue("");
    expect(screen.queryByText(t("catalogMetaUnsaved"))).toBeNull();
  });

  it("keeps curation form locked across collapse and reopen while a save is pending", async () => {
    const user = userEvent.setup();
    let resolveSave!: () => void;
    const onCurate = vi.fn(
      () => new Promise<void>((resolve) => {
        resolveSave = resolve;
      }),
    );
    const paper: ResearchRecord = {
      id: "src-pending-1",
      kind: "source",
      data: { title: "Pending Save Paper", locator: "https://example.org/p", year: "2024" },
    };
    render(
      <LiteratureLibrary
        sources={[paper]}
        screenings={[]}
        curations={[]}
        t={t}
        onScreen={vi.fn()}
        onCurate={onCurate}
        onPrepare={vi.fn()}
      />,
    );
    await user.click(screen.getByText(t("catalogEditMeta")));
    const form = screen.getByRole("button", { name: t("catalogSaveMeta") }).closest("form")!;
    await user.type(within(form).getByLabelText(t("catalogRelevance")), "Initial pending note");
    await user.click(within(form).getByRole("button", { name: t("catalogSaveMeta") }));

    // Collapse and reopen while save is still pending: fieldset must stay disabled.
    await user.click(screen.getByText(t("catalogEditMeta")));
    await user.click(screen.getByText(t("catalogEditMeta")));
    const reopenedField = screen.getByLabelText(t("catalogRelevance"));
    expect(reopenedField).toBeDisabled();
    expect(reopenedField).toHaveValue("Initial pending note");
    expect(screen.getByRole("button", { name: t("saving") })).toBeDisabled();

    resolveSave();
    await waitFor(() => {
      expect(screen.getByLabelText(t("catalogRelevance"))).toBeEnabled();
    });
    expect(within(screen.getByRole("button", { name: t("catalogSaveMeta") }).closest("form")!).getByRole("status")).toHaveTextContent(t("saved"));
  });

  it("preserves structured author boundaries and allows clearing inherited abstract and journal", async () => {
    const user = userEvent.setup();
    const onCurate = vi.fn().mockResolvedValue(undefined);
    const structured: ResearchRecord = {
      id: "src-struct-1",
      kind: "source",
      data: {
        title: "Structured Authors Study",
        locator: "https://example.org/struct",
        authors: [
          { family: "Smith", given: "John" },
          { family: "Doe", given: "Jane" },
        ],
        journal: "Nature Methods",
        abstract: "Original abstract from import.",
      },
    };
    const { rerender } = render(
      <LiteratureLibrary
        sources={[structured]}
        screenings={[]}
        curations={[]}
        t={t}
        onScreen={vi.fn()}
        onCurate={onCurate}
        onPrepare={vi.fn()}
      />,
    );
    await user.click(screen.getByText(t("catalogEditMeta")));
    const form = screen.getByRole("button", { name: t("catalogSaveMeta") }).closest("form")!;
    expect(within(form).getByLabelText(t("catalogMetaAuthors"))).toHaveValue("Smith, John; Doe, Jane");

    // Editing only category must not overwrite structured authors with broken comma splits.
    await user.type(within(form).getByLabelText(t("catalogCategory")), "human");
    await user.click(within(form).getByRole("button", { name: t("catalogSaveMeta") }));
    expect(onCurate).toHaveBeenLastCalledWith("src-struct-1", { category: "human" });

    // Editing authors with semicolon keeps internal commas intact, and clearing venue/summary overrides journal/abstract.
    await user.type(within(form).getByLabelText(t("catalogMetaAuthors")), "; Lee, Amy");
    await user.clear(within(form).getByLabelText(t("catalogMetaVenue")));
    await user.clear(within(form).getByLabelText(t("catalogMetaSummary")));
    await user.click(within(form).getByRole("button", { name: t("catalogSaveMeta") }));
    expect(onCurate).toHaveBeenLastCalledWith("src-struct-1", {
      authors: ["Smith, John", "Doe, Jane", "Lee, Amy"],
      venue: "",
      summary: "",
    });

    const clearedCurations: ResearchRecord[] = [
      {
        id: "cur-clear",
        kind: "source_curation",
        data: {
          source_id: "src-struct-1",
          authors: ["Smith, John", "Doe, Jane", "Lee, Amy"],
          venue: "",
          summary: "",
        },
      },
    ];
    rerender(
      <LiteratureLibrary
        sources={[structured]}
        screenings={[]}
        curations={clearedCurations}
        t={t}
        onScreen={vi.fn()}
        onCurate={onCurate}
        onPrepare={vi.fn()}
      />,
    );
    expect(screen.queryByText("Original abstract from import.")).toBeNull();
    expect(screen.queryByText(/Nature Methods/)).toBeNull();
    expect(structured.data.abstract).toBe("Original abstract from import.");
    expect(structured.data.journal).toBe("Nature Methods");
  });

  it("renders a primary CTA button in empty literature view that opens the add/search panel", async () => {
    const user = userEvent.setup();
    const onOpenAddTools = vi.fn();
    render(
      <LiteratureLibrary
        sources={[]}
        screenings={[]}
        t={t}
        onScreen={vi.fn()}
        onPrepare={vi.fn()}
        onOpenAddTools={onOpenAddTools}
      />,
    );
    await user.click(screen.getByRole("button", { name: t("catalogAddFirstSource") }));
    expect(onOpenAddTools).toHaveBeenCalledTimes(1);
  });
});
