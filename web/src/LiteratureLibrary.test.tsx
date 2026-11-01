import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LiteratureLibrary } from "./LiteratureLibrary";
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
    expect(screen.getByText(t("catalogOrganizationHelp"))).toBeVisible();
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
    expect(screen.getByRole("searchbox", {name:tr("catalogSearch")})).toBeVisible();
    screen.getByRole("button", {name:`${tr("catalogNeedsCategory")} (1)`}).focus();
    await user.keyboard("{Enter}");
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(1);
    screen.getByRole("button", {name:tr("catalogClearFilters")}).focus();
    await user.keyboard("{Enter}");
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(4);
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
});
