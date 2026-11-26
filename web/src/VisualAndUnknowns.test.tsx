import { useState } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CommandPalette, useCommandPaletteShortcut } from "./CommandPalette";
import { SynthesisMatrix } from "./SynthesisMatrix";
import type { Page, Project, ResearchRecord } from "./types";
import {
  computeResearchBlindSpots,
  EvidenceBlindSpotRadar,
  LiteratureVisualCharts,
  ResearchStageStepper,
} from "./VisualInsights";

const makeSource = (
  id: string,
  overrides: Record<string, unknown> = {},
): ResearchRecord => ({
  id,
  kind: "source",
  data: {
    title: `Paper ${id}`,
    year: "2024",
    reading_scope: "full-text",
    doi: `10.1000/${id}`,
    summary: `Summary for ${id}`,
    authors: ["Ada Lovelace", "Alan Turing"],
    tags: ["llm", "method:benchmark"],
    ...overrides,
  },
});

const makeScreening = (
  id: string,
  sourceId: string,
  decision: "include" | "exclude",
  rationale = "Screened by researcher",
): ResearchRecord => ({
  id,
  kind: "screening",
  data: {
    source_id: sourceId,
    decision,
    rationale,
  },
});

const makeClaim = (
  id: string,
  text: string,
  sourceIds: string[],
): ResearchRecord => ({
  id,
  kind: "claim",
  data: {
    text,
    source_ids: sourceIds,
    verification_status: "unverified",
  },
});

describe("VisualInsights & Blind-Spot Radar", () => {
  it("detects abstract-only claims, single-source claims, uncited included papers, and DOI/summary gaps", () => {
    const sources: ResearchRecord[] = [
      // Full-text, included, cited, complete metadata
      makeSource("s-solid", {
        title: "Solid Full-Text Study",
        reading_scope: "full-text",
        doi: "10.1038/solid-2025",
        summary: "Verified full-text findings.",
      }),
      // Abstract-only, included, cited, missing DOI
      makeSource("s-abs-nodoi", {
        title: "Abstract Only Missing DOI",
        reading_scope: "abstract",
        doi: "",
        summary: "Saved abstract snippet.",
      }),
      // Full-text, included, UNCITED, missing summary
      makeSource("s-orphan-nosum", {
        title: "Orphan Included Paper",
        reading_scope: "full-text",
        doi: "10.1145/orphan-2024",
        summary: "   ",
        abstract: "",
      }),
      // Excluded paper (should never count as uncited included or metadata gap)
      makeSource("s-excluded", {
        title: "Excluded Paper",
        reading_scope: "metadata",
        doi: "",
        summary: "",
      }),
    ];

    const screenings: ResearchRecord[] = [
      makeScreening("scr-1", "s-solid", "include"),
      makeScreening("scr-2", "s-abs-nodoi", "include"),
      makeScreening("scr-3", "s-orphan-nosum", "include"),
      makeScreening("scr-4", "s-excluded", "exclude"),
    ];

    const claims: ResearchRecord[] = [
      // Abstract-only AND single-source
      makeClaim("c-risky", "Claim grounded only on an abstract", ["s-abs-nodoi"]),
      // Multi-source with at least 1 full-text (safe on both counts)
      makeClaim("c-robust", "Triangulated claim with full text", ["s-solid", "s-abs-nodoi"]),
      // Unlinked claim (0 sources -> neither abstract-only nor single-source)
      makeClaim("c-unlinked", "Draft unlinked hypothesis", []),
    ];

    const blindSpots = computeResearchBlindSpots(sources, screenings, claims);

    expect(blindSpots.abstractOnlyClaims.map((c) => c.id)).toEqual(["c-risky"]);
    expect(blindSpots.singleSourceClaims.map((c) => c.id)).toEqual(["c-risky"]);
    expect(blindSpots.uncitedIncludedSources.map((s) => s.id)).toEqual(["s-orphan-nosum"]);
    expect(blindSpots.metadataGapSources.map((s) => s.id)).toEqual([
      "s-abs-nodoi",
      "s-orphan-nosum",
    ]);
    expect(blindSpots.robustnessScore).toBeGreaterThan(0);
    expect(blindSpots.robustnessScore).toBeLessThan(100);
  });

  it("renders EvidenceBlindSpotRadar in zh-TW and triggers jump callbacks", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    const onOpenPaper = vi.fn();

    const s1 = makeSource("s1", { title: "Abstract Paper", reading_scope: "abstract" });
    const s2 = makeSource("s2", { title: "Uncited Paper", doi: "" });
    const screenings = [
      makeScreening("sc1", "s1", "include"),
      makeScreening("sc2", "s2", "include"),
    ];
    const claims = [makeClaim("c1", "Fragile abstract claim", ["s1"])];

    render(
      <EvidenceBlindSpotRadar
        sources={[s1, s2]}
        screenings={screenings}
        claims={claims}
        locale="zh-TW"
        onNavigate={onNavigate}
        onOpenPaper={onOpenPaper}
      />,
    );

    expect(screen.getByRole("heading", { name: "證據風險與研究盲點雷達" })).toBeVisible();
    expect(screen.getByText("1 項高風險")).toBeVisible();
    expect(screen.getAllByText("1 項需留意")).toHaveLength(3);

    const evidenceButtons = screen.getAllByRole("button", { name: /檢視證據/ });
    await user.click(evidenceButtons[0]);
    expect(onNavigate).toHaveBeenCalledWith("evidence", "record-c1");

    const litButtons = screen.getAllByRole("button", { name: /開啟文獻/ });
    await user.click(litButtons[0]);
    expect(onOpenPaper).toHaveBeenCalledWith(s2);
  });

  it("renders ResearchStageStepper and LiteratureVisualCharts with interactive year bar callback", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    const onSelectYear = vi.fn();
    const onSelectScope = vi.fn();

    const sources = [
      makeSource("p2023", { year: "2023", reading_scope: "abstract" }),
      makeSource("p2024a", { year: "2024", reading_scope: "full-text" }),
      makeSource("p2024b", { year: "2024", reading_scope: "metadata" }),
      makeSource("p2025", { year: "2025", reading_scope: "full-text" }),
    ];
    const screenings = [
      makeScreening("sc1", "p2024a", "include"),
      makeScreening("sc2", "p2025", "include"),
    ];
    const claims = [makeClaim("c1", "Supported claim", ["p2024a", "p2025"])];

    render(
      <>
        <ResearchStageStepper
          sources={sources}
          screenings={screenings}
          claims={claims}
          locale="zh-TW"
          onNavigate={onNavigate}
        />
        <LiteratureVisualCharts
          sources={sources}
          screenings={screenings}
          locale="zh-TW"
          onSelectYear={onSelectYear}
          onSelectScope={onSelectScope}
        />
      </>,
    );

    await user.click(screen.getByRole("button", { name: /3\. 證據主張/ }));
    expect(onNavigate).toHaveBeenCalledWith("evidence");

    // Donut center KPI shows Included 2/4
    expect(screen.getByText("2/4")).toBeVisible();

    // Clicking year 2024 bar triggers onSelectYear("2024")
    const year2024Btn = screen.getByRole("button", { name: /2024 年：共 2 篇/ });
    await user.click(year2024Btn);
    expect(onSelectYear).toHaveBeenCalledWith("2024");

    // Clicking donut scope legend triggers onSelectScope("full")
    await user.click(screen.getByRole("button", { name: /全文.*2.*\(50%\)/ }));
    expect(onSelectScope).toHaveBeenCalledWith("full");
  });
});

describe("SynthesisMatrix", () => {
  it("renders claim citation counts, top 6 semantic label columns, tag dots, and selects papers", async () => {
    const user = userEvent.setup();
    const onSelectPaper = vi.fn();
    const onToggleTag = vi.fn();

    const p1 = makeSource("p1", {
      title: "Generative Agents Architecture",
      year: "2023",
      reading_scope: "full-text",
      tags: [
        "llm",
        "method:simulation",
        "domain:social",
        "benchmark",
        "memory",
        "planning",
        "seventh-rare-tag",
      ],
    });
    const p2 = makeSource("p2", {
      title: "Hydrology Digital Twin",
      year: "2025",
      reading_scope: "abstract",
      tags: ["method:simulation", "domain:hydrology"],
    });

    const screenings = [makeScreening("sc-p1", "p1", "include")];
    const claims = [
      makeClaim("c1", "Claim 1", ["p1"]),
      makeClaim("c2", "Claim 2", ["p1"]),
    ];

    render(
      <SynthesisMatrix
        sources={[p1, p2]}
        screenings={screenings}
        claims={claims}
        locale="zh-TW"
        selectedId="p1"
        onSelectPaper={onSelectPaper}
        onToggleTag={onToggleTag}
        selectedTags={["method:simulation"]}
      />,
    );

    const table = screen.getByRole("table");
    // Top 6 tags appear as column headers; method:simulation has count 2 and is pressed
    const simHeaderBtn = within(table).getByRole("button", { name: /#method.*simulation.*2/i });
    expect(simHeaderBtn).toHaveAttribute("aria-pressed", "true");
    await user.click(simHeaderBtn);
    expect(onToggleTag).toHaveBeenCalledWith("method:simulation");

    // Claim counts: p1 cited by 2 claims, p2 cited by 0 claims
    expect(within(table).getByLabelText("被 2 條證據主張引用")).toHaveTextContent("2");
    expect(within(table).getByLabelText("被 0 條證據主張引用")).toHaveTextContent("0");

    // Tag dot aria-label confirms p2 carries #method:simulation
    expect(
      within(table).getByRole("img", { name: "Hydrology Digital Twin 標記有 #method:simulation" }),
    ).toBeVisible();

    // Clicking paper title invokes onSelectPaper
    await user.click(
      within(table).getByRole("button", { name: /Hydrology Digital Twin/ }),
    );
    expect(onSelectPaper).toHaveBeenCalledWith(p2);
  });
});

describe("CommandPalette & Ctrl+K Shortcut", () => {
  const projects: Project[] = [
    { id: "proj-alpha", title: "Alpha Multi-Agent Review", archetype: "review", goal: "Synthesize ABM" },
    { id: "proj-beta", title: "Beta Basin Hydrology", archetype: "empirical", goal: "Calibrate runoff" },
  ];

  const papers: ResearchRecord[] = [
    makeSource("paper-1", {
      title: "Emergent Social Personas in Sandboxes",
      authors: ["Joon Sung Park"],
      year: "2023",
      doi: "10.1145/3586183.3606763",
      tags: ["persona", "method:abm"],
    }),
    makeSource("paper-2", {
      title: "Distributed Flood Forecasting",
      authors: ["Mei-Ling Chen"],
      year: "2025",
      doi: "10.1029/2025WR099999",
      tags: ["domain:hydrology"],
    }),
  ];

  function PaletteHarness({
    onSelectProject = vi.fn(),
    onOpenPaper = vi.fn(),
    onNavigate = vi.fn(),
    onOpenSettings = vi.fn(),
    onToggleTheme = vi.fn(),
  }: {
    onSelectProject?: (id: string) => void;
    onOpenPaper?: (paper: ResearchRecord) => void;
    onNavigate?: (page: Page) => void;
    onOpenSettings?: () => void;
    onToggleTheme?: () => void;
  }) {
    const [open, setOpen] = useState(false);
    useCommandPaletteShortcut(() => setOpen((prev) => !prev));
    return (
      <div>
        <button type="button" onClick={() => setOpen(true)}>
          Trigger Palette
        </button>
        <CommandPalette
          open={open}
          onClose={() => setOpen(false)}
          projects={projects}
          currentProjectId="proj-alpha"
          onSelectProject={onSelectProject}
          sources={papers}
          onOpenPaper={onOpenPaper}
          onNavigate={onNavigate}
          onOpenSettings={onOpenSettings}
          onToggleTheme={onToggleTheme}
          resolvedTheme="light"
          locale="zh-TW"
        />
      </div>
    );
  }

  it("toggles via Ctrl+K, filters by title/DOI/#tag, and navigates with ArrowDown/ArrowUp/Enter/Escape", async () => {
    const user = userEvent.setup();
    const onOpenPaper = vi.fn();
    const onSelectProject = vi.fn();
    const onToggleTheme = vi.fn();

    render(
      <PaletteHarness
        onOpenPaper={onOpenPaper}
        onSelectProject={onSelectProject}
        onToggleTheme={onToggleTheme}
      />,
    );

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    // Open with Ctrl+K
    await user.keyboard("{Control>}k{/Control}");
    const dialog = screen.getByRole("dialog", { name: "全域指令面板" });
    expect(dialog).toBeVisible();

    // First quick action is Toggle Dark Mode — press Enter immediately to execute
    await user.keyboard("{Enter}");
    expect(onToggleTheme).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    // Re-open with Meta+K and filter by #tag
    await user.keyboard("{Meta>}k{/Meta}");
    expect(screen.getByRole("dialog", { name: "全域指令面板" })).toBeVisible();

    const searchBox = screen.getByRole("textbox", { name: "全域指令面板" });
    await user.type(searchBox, "#hydrology");
    expect(screen.getByRole("option", { name: /Distributed Flood Forecasting/ })).toBeVisible();
    expect(screen.queryByRole("option", { name: /Emergent Social Personas/ })).not.toBeInTheDocument();

    await user.keyboard("{Enter}");
    expect(onOpenPaper).toHaveBeenCalledWith(papers[1]);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    // Re-open, filter projects, navigate with ArrowDown/ArrowUp, and close with Escape
    await user.keyboard("{Control>}k{/Control}");
    const searchBox2 = screen.getByRole("textbox", { name: "全域指令面板" });
    await user.type(searchBox2, "Basin");
    expect(screen.getByRole("option", { name: /Beta Basin Hydrology/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await user.keyboard("{ArrowDown}{ArrowUp}{Enter}");
    expect(onSelectProject).toHaveBeenCalledWith("proj-beta");

    await user.keyboard("{Control>}k{/Control}");
    expect(screen.getByRole("dialog")).toBeVisible();
    const searchBoxDoi = screen.getByRole("textbox", { name: "全域指令面板" });
    await user.type(searchBoxDoi, "10.1145/3586183");
    expect(screen.getByRole("option", { name: /Emergent Social Personas/ })).toBeVisible();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("respects emil-design-eng & dark-mode CSS guardrails in visuals.css", async () => {
    const fsMod = (await import(/* @vite-ignore */ ("node:" + "fs"))) as {
      readFileSync: (path: string, encoding: string) => string;
    };
    const visualsCss = fsMod.readFileSync("src/visuals.css", "utf8");
    expect(visualsCss).not.toMatch(/transition\s*:\s*all\b/i);
    expect(visualsCss).not.toMatch(/#[fF]{3,6}\b/);
    expect(visualsCss).not.toMatch(/#000000\b/);
    expect(visualsCss).not.toMatch(/border-(?:left|right)\s*:\s*[2-9]px\s+solid/);
    expect(visualsCss).not.toMatch(/:root\s*\{/);
    expect(visualsCss).toMatch(/\.vr-cmd-dialog[\s\S]*?transition:\s*none/);
    expect(visualsCss).toMatch(/scale\(0\.97\)/);
    expect(visualsCss).toMatch(/@media\s*\(hover:\s*hover\)\s*and\s*\(pointer:\s*fine\)/);
  });

  it("penalizes unlinked claims, separates unknown reading scopes from metadata, distinguishes authority binding from delivery readiness, and traps Tab in CommandPalette", async () => {
    const user = userEvent.setup();

    // 1. Unlinked claims never produce 100% robustness or inflate score
    const unlinkedOnly = computeResearchBlindSpots(
      [],
      [],
      [makeClaim("c-empty", "Unsupported claim", [])],
    );
    expect(unlinkedOnly.robustnessScore).toBeLessThanOrEqual(35);

    const solidSource = makeSource("s-full", { reading_scope: "full-text" });
    const inc = [makeScreening("sc-full", "s-full", "include")];
    const allGrounded = computeResearchBlindSpots(
      [solidSource],
      inc,
      [makeClaim("c-ok-1", "Claim 1", ["s-full"]), makeClaim("c-ok-2", "Claim 2", ["s-full"])],
    );
    const withUnsupported = computeResearchBlindSpots(
      [solidSource],
      inc,
      [
        makeClaim("c-ok-1", "Claim 1", ["s-full"]),
        makeClaim("c-ok-2", "Claim 2", ["s-full"]),
        makeClaim("c-unlinked", "Unsupported", []),
      ],
    );
    expect(withUnsupported.robustnessScore).toBeLessThan(allGrounded.robustnessScore);

    // 2. Unknown scope stays distinct from metadata in LiteratureVisualCharts & SynthesisMatrix,
    //    caller-supplied data.screening is NOT promoted to Included without a saved screening record,
    //    and bound manuscript authority stays distinct from Ready delivery in ResearchStageStepper
    const onSelectScope = vi.fn();
    const unknownSrc = makeSource("s-unk", { reading_scope: "", screening: "include" });
    render(
      <>
        <ResearchStageStepper
          sources={[unknownSrc]}
          screenings={[]}
          claims={[]}
          manuscript={{ project: { id: "proj-alpha" }, artifacts: [] }}
          locale="en"
          onNavigate={vi.fn()}
        />
        <LiteratureVisualCharts
          sources={[unknownSrc]}
          screenings={[]}
          locale="en"
          onSelectScope={onSelectScope}
        />
        <SynthesisMatrix
          sources={[unknownSrc]}
          screenings={[]}
          locale="en"
          onSelectPaper={vi.fn()}
        />
      </>,
    );

    expect(screen.getByText("0/1 in")).toBeVisible();
    expect(screen.getByText("Authority bound")).toBeVisible();
    expect(screen.queryByText("Ready")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Metadata.*0.*\(0%\)/ })).toBeVisible();
    const unknownScopeBtn = screen.getByRole("button", { name: /Unknown.*1.*\(100%\)/ });
    await user.click(unknownScopeBtn);
    expect(onSelectScope).toHaveBeenCalledWith("unknown");
    expect(within(screen.getByRole("table")).getByText(/Unknown/)).toBeVisible();

    // 3. CommandPalette traps Tab focus inside modal and calls scrollIntoView on active option
    const scrollSpy = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollSpy,
    });
    try {
      render(<PaletteHarness />);
      const triggerBtn = screen.getByRole("button", { name: "Trigger Palette" });
      triggerBtn.focus();
      await user.click(triggerBtn);
      const searchBox = screen.getByRole("textbox", { name: "全域指令面板" });
      expect(searchBox).toHaveFocus();
      await user.keyboard("{Tab}");
      expect(searchBox).toHaveFocus();
      await user.keyboard("{ArrowDown}");
      expect(scrollSpy).toHaveBeenCalled();
    } finally {
      // @ts-expect-error cleanup test prototype spy
      delete HTMLElement.prototype.scrollIntoView;
    }
  });
});
