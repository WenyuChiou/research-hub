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
