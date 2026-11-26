import { useState } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  buildApaBibliography,
  buildCslJsonExport,
  buildObsidianBaseYaml,
  buildObsidianUri,
  buildRisExport,
  extractVaultName,
  formatApaReference,
  formatInTextCitation,
  formatLatexCite,
  formatPandocCite,
  makeCiteKey,
} from "./citations";
import {
  LiteratureLibrary,
  type QuickAddSourceInput,
  type SourceCurationInput,
} from "./LiteratureLibrary";
import { ProjectPages } from "./Pages";
import { translator } from "./i18n";
import type { ProjectDetail, ResearchRecord, Workspace } from "./types";

const tEn = translator("en");

const initialSources: ResearchRecord[] = [
  {
    id: "src-1",
    kind: "source",
    data: {
      title: "Generative Agents: Interactive Simulacra of Human Behavior",
      authors: ["Joon Sung Park", "Joseph C. O'Brien", "Michael S. Bernstein"],
      year: "2023",
      venue: "UIST 2023",
      category: "llm-agents",
      tags: ["multi-agent", "validation", "memory"],
      reading_scope: "full-text",
      doi: "10.1145/3586183.3606763",
      locator: "https://doi.org/10.1145/3586183.3606763",
      summary: "Introduces memory, reflection, and planning for believable LLM agents.",
      identity_status: "unverified",
    },
  },
  {
    id: "src-2",
    kind: "source",
    data: {
      title: "Coupling Large Language Models with Hydrological Water Allocation",
      authors: ["Hao Du", "Lin Wei"],
      year: "2024",
      venue: "Water Resources Research",
      category: "water-abm",
      tags: ["multi-agent", "validation", "hydrology"],
      reading_scope: "full-text",
      doi: "10.1029/2024WR037001",
      locator: "https://doi.org/10.1029/2024WR037001",
      summary: "Couples cognitive agent rules with basin reservoir operations.",
      identity_status: "unverified",
    },
  },
  {
    id: "src-3",
    kind: "source",
    data: {
      title: "Synthetic Replacements for Human Survey Data",
      authors: [{ family: "Bisbee", given: "James" }],
      year: "2024",
      venue: "Political Analysis",
      category: "evaluation-methods",
      tags: ["bias", "multi-agent"],
      reading_scope: "abstract",
      doi: "https://doi.org/10.1017/pan.2024.5",
      locator: "https://doi.org/10.1017/pan.2024.5",
      abstract: "Evaluates variance collapse and prompt sensitivity in synthetic panels.",
      identity_status: "unverified",
    },
  },
  {
    id: "src-4",
    kind: "source",
    data: {
      title: "Reflexion: Language Agents with Verbal Reinforcement Learning",
      authors: ["Noah Shinn", "Federico Cassano"],
      year: "2023",
      venue: "NeurIPS 2023",
      category: "llm-agents",
      tags: ["reasoning"],
      reading_scope: "metadata",
      locator: "https://arxiv.org/abs/2303.11366",
      identity_status: "unverified",
    },
  },
];

const initialScreenings: ResearchRecord[] = [
  {
    id: "scr-1",
    kind: "screening",
    data: { source_id: "src-1", decision: "include", rationale: "Landmark full-text paper." },
  },
  {
    id: "scr-2",
    kind: "screening",
    data: { source_id: "src-2", decision: "include", rationale: "Core basin ABM benchmark." },
  },
  {
    id: "scr-4",
    kind: "screening",
    data: { source_id: "src-4", decision: "exclude", rationale: "Out of empirical scope." },
  },
];

const mockWorkspace: Workspace = {
  ok: true,
  projects: [{ id: "proj-1", title: "Multi-Topic Benchmark", archetype: "review", goal: "Evaluate literature" }],
  protection_scope: "local-only",
  capabilities: {
    codex: { status: "unavailable", message: "No runner" },
    writing: { status: "unavailable", message: "No adapter" },
    approval: { status: "available", message: "Human review" },
    obsidian_validation: {
      version: 1,
      status: "available",
      read_only: true,
      scope: "explicit",
      authorized_vault: "C:\\temp\\ag-runs\\user-e2e-20\\vault",
    },
    local_integrations: {
      version: 1,
      status: "available",
      zotero_configured: true,
      nlm_state_present: true,
      obsidian_cli_present: true,
      obsidian_vault_configured: true,
      obsidian_vault_name: "vault",
    },
  },
};

describe("Literature CRUD, multi-dimensional filters, academic citations, Obsidian Bases & Evidence UI", () => {
  it("supports end-to-end Add, Edit (DOI + labels), Remove (Archive), and Restore without mutating source identity", async () => {
    const user = userEvent.setup();

    function StatefulLibraryHarness() {
      const [sources, setSources] = useState<ResearchRecord[]>(initialSources.slice(0, 3));
      const [curations, setCurations] = useState<ResearchRecord[]>([]);

      const handleAdd = async (payload: QuickAddSourceInput) => {
        setSources((prev) => [
          ...prev,
          {
            id: `src-added-${prev.length + 1}`,
            kind: "source",
            data: {
              ...payload,
              identity_status: "unverified",
            },
          },
        ]);
      };

      const handleCurate = async (sourceId: string, patch: SourceCurationInput) => {
        setCurations((prev) => [
          ...prev,
          {
            id: `cur-${prev.length + 1}`,
            kind: "source_curation",
            data: {
              source_id: sourceId,
              ...patch,
            },
          },
        ]);
      };

      return (
        <LiteratureLibrary
          sources={sources}
          curations={curations}
          screenings={[]}
          t={tEn}
          onScreen={vi.fn()}
          onCurate={handleCurate}
          onAddSource={handleAdd}
          onPrepare={vi.fn()}
        />
      );
    }

    render(<StatefulLibraryHarness />);
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(3);

    // 1. Quick Add a new clinical AI paper
    await user.click(screen.getByRole("button", { name: tEn("catalogQuickAdd") }));
    const addRegion = screen.getByRole("region", { name: tEn("catalogQuickAddTitle") });
    fireEvent.change(within(addRegion).getByLabelText(new RegExp(`^${tEn("title")}`)), { target: { value: "Clinical AI Sepsis Triage Trial" } });
    fireEvent.change(within(addRegion).getByLabelText(new RegExp(`^${tEn("locator")}`)), { target: { value: "https://doi.org/10.1038/s41591-025-00111-2" } });
    fireEvent.change(within(addRegion).getByLabelText(tEn("doi")), { target: { value: "10.1038/s41591-025-00111-2" } });
    await user.selectOptions(within(addRegion).getByLabelText(tEn("catalogDeclareScope")), "full-text");
    fireEvent.change(within(addRegion).getByLabelText(tEn("catalogCategory")), { target: { value: "clinical-ai" } });
    fireEvent.change(within(addRegion).getByLabelText(tEn("catalogYear")), { target: { value: "2025" } });
    fireEvent.change(within(addRegion).getByLabelText(tEn("catalogMetaAuthors")), { target: { value: "Elena Vance, Marcus Chen" } });
    fireEvent.change(within(addRegion).getByLabelText(tEn("catalogMetaVenue")), { target: { value: "Nature Medicine" } });
    fireEvent.change(within(addRegion).getByLabelText(tEn("catalogMetaTags")), { target: { value: "#domain:clinical, rct" } });
    fireEvent.change(within(addRegion).getByLabelText(tEn("catalogMetaSummary")), { target: { value: "Multi-site randomized trial of bedside AI alerts." } });
    await user.click(within(addRegion).getByRole("button", { name: tEn("addSource") }));

    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(4);

    // Select the newly added paper and verify inline citation
    await user.click(within(screen.getByRole("table")).getByRole("button", { name: "Clinical AI Sepsis Triage Trial" }));
    const detail = screen.getByRole("complementary", { name: tEn("catalogDetail") });
    expect(within(detail).getByText("(Vance & Chen, 2025)")).toBeVisible();

    // 2. Edit DOI and Venue via Category & details curation
    await user.click(within(detail).getByText(tEn("catalogEditMeta")));
    const editForm = within(detail).getByRole("button", { name: tEn("catalogSaveMeta") }).closest("form")!;
    const doiInput = within(editForm).getByLabelText(tEn("doi"));
    expect(doiInput).toHaveValue("10.1038/s41591-025-00111-2");
    fireEvent.change(doiInput, { target: { value: "10.1038/s41591-025-99999-9" } });
    const venueInput = within(editForm).getByLabelText(tEn("catalogMetaVenue"));
    fireEvent.change(venueInput, { target: { value: "The Lancet Digital Health" } });
    await user.click(within(editForm).getByRole("button", { name: tEn("catalogSaveMeta") }));

    expect(within(detail).getByText(/The Lancet Digital Health/)).toBeVisible();

    // 3. Remove (Archive) the paper and verify active list drops to 3 and Archived (1) appears
    await user.click(within(detail).getByRole("button", { name: tEn("catalogArchiveSource") }));
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(3);

    const organizeGroup = screen.getByRole("group", { name: tEn("catalogOrganize") });
    const archivedTab = within(organizeGroup).getByRole("button", { name: /Archived \(1\)/i });
    await user.click(archivedTab);
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(1);
    expect(within(detail).getByText(tEn("catalogArchivedNotice"))).toBeVisible();

    // 4. Restore the archived paper back to active list
    await user.click(within(detail).getByRole("button", { name: tEn("catalogRestoreSource") }));
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(4);
    expect(within(organizeGroup).queryByRole("button", { name: /Archived/i })).toBeNull();
  });

  it("combines Included/Excluded screening tabs, multi-label intersection, and Year dropdown, then clears all", async () => {
    const user = userEvent.setup();
    render(
      <LiteratureLibrary
        sources={initialSources}
        screenings={initialScreenings}
        t={tEn}
        onScreen={vi.fn()}
        onPrepare={vi.fn()}
      />,
    );

    const organizeGroup = screen.getByRole("group", { name: tEn("catalogOrganize") });
    // Included (2)
    await user.click(within(organizeGroup).getByRole("button", { name: /^Included \(2\)$/ }));
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(2);

    // Excluded (1)
    await user.click(within(organizeGroup).getByRole("button", { name: /^Excluded \(1\)$/ }));
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(1);
    expect(screen.getByRole("heading", { name: /Reflexion/ })).toBeVisible();

    // Reset via Clear filters
    await user.click(screen.getByRole("button", { name: tEn("catalogClearFilters") }));
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(4);

    // Multi-label combinatorial toggle: #multi-agent (3) AND #validation (2) => 2 papers
    const tagGroup = screen.getByRole("group", { name: tEn("catalogFilterByTag") });
    const multiAgentBtn = within(tagGroup).getByRole("button", { name: /#multi-agent/i });
    const validationBtn = within(tagGroup).getByRole("button", { name: /#validation/i });

    await user.click(multiAgentBtn);
    expect(multiAgentBtn).toHaveAttribute("aria-pressed", "true");
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(3);

    await user.click(validationBtn);
    expect(validationBtn).toHaveAttribute("aria-pressed", "true");
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(2);

    // Narrow further by Year = 2024 => 1 paper (Coupling Large Language Models with Hydrological Water Allocation)
    const yearSelect = screen.getByLabelText(tEn("catalogFilterYear"));
    await user.selectOptions(yearSelect, "2024");
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(1);
    expect(screen.getByRole("heading", { name: /Hydrological Water Allocation/ })).toBeVisible();

    // Clear all filters at once
    await user.click(screen.getByRole("button", { name: tEn("catalogClearFilters") }));
    expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(4);
    expect(multiAgentBtn).toHaveAttribute("aria-pressed", "false");
    expect(validationBtn).toHaveAttribute("aria-pressed", "false");
  });

  it("generates accurate APA 7th, RIS (.ris), CSL-JSON, BibTeX, Obsidian Base (.base), and obsidian:// links", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });

    // Unit checks on citation formatters
    expect(makeCiteKey(initialSources[0])).toBe("park2023generative");
    expect(formatInTextCitation(initialSources[0])).toBe("(Park et al., 2023)");
    expect(formatInTextCitation(initialSources[1])).toBe("(Du & Wei, 2024)");
    expect(formatInTextCitation(initialSources[2])).toBe("(Bisbee, 2024)");
    expect(formatPandocCite(initialSources[0])).toBe("[@park2023generative]");
    expect(formatLatexCite(initialSources[0])).toBe("\\cite{park2023generative}");

    const apa = formatApaReference(initialSources[0]);
    expect(apa).toContain("Park, J. S., O'Brien, J. C., & Bernstein, M. S. (2023).");
    expect(apa).toContain("Generative Agents: Interactive Simulacra of Human Behavior.");
    expect(apa).toContain("UIST 2023.");
    expect(apa).toContain("https://doi.org/10.1145/3586183.3606763");

    const apaBib = buildApaBibliography(initialSources.slice(0, 3));
    expect(apaBib.indexOf("Bisbee, J.")).toBeLessThan(apaBib.indexOf("Du, H."));

    const ris = buildRisExport(initialSources.slice(0, 3));
    expect(ris).toContain("TY  - JOUR");
    expect(ris).toContain("TI  - Generative Agents: Interactive Simulacra of Human Behavior");
    expect(ris).toContain("AU  - Park, Joon Sung");
    expect(ris).toContain("DO  - 10.1145/3586183.3606763");
    expect(ris).toContain("DO  - 10.1017/pan.2024.5");
    expect(ris).toContain("KW  - multi-agent");
    expect(ris).toContain("N1  - Reading scope: full-text; Identity: unverified");
    expect(ris).toContain("ER  - ");

    const csl = JSON.parse(buildCslJsonExport(initialSources.slice(0, 3))) as Array<Record<string, unknown>>;
    expect(csl).toHaveLength(3);
    expect(csl[0].id).toBe("park2023generative");
    expect(csl[0].DOI).toBe("10.1145/3586183.3606763");
    expect(csl[0].issued).toEqual({ "date-parts": [[2023]] });
    expect(csl[2].author).toEqual([{ family: "Bisbee", given: "James" }]);

    const baseYaml = buildObsidianBaseYaml("llm-social-sim", "LLM Social Simulation", initialSources.slice(0, 2));
    expect(baseYaml).toContain('topic_cluster == "llm-social-sim"');
    expect(baseYaml).toContain('doi == "10.1145/3586183.3606763"');
    expect(baseYaml).toContain('LLM Social Simulation — Literature Export (2)');
    expect(baseYaml).toContain('name: "All Literature"');
    expect(baseYaml).toContain('name: "Included Cohort"');
    expect(baseYaml).toContain('name: "Needs Full-Text or Triage"');

    // 20-author APA must retain all 20 authors including author #19
    const twentyAuthorRecord: ResearchRecord = {
      id: "src-20a",
      kind: "source",
      data: {
        title: "Twenty Author Consortium Study.",
        authors: Array.from({ length: 20 }, (_, i) => `Jane Author${i + 1}`),
        year: "2025",
        venue: "Science",
        doi: "doi: 10.1126/science.2025.20",
      },
    };
    const twentyApa = formatApaReference(twentyAuthorRecord);
    expect(twentyApa).toContain("Author19, J., & Author20, J. (2025).");
    expect(twentyApa).toContain("https://doi.org/10.1126/science.2025.20");

    expect(extractVaultName("C:\\temp\\ag-runs\\user-e2e-20\\vault\\")).toBe("vault");
    expect(extractVaultName("C:\\")).toBe("");
    expect(extractVaultName("/Users/researcher/knowledge-base")).toBe("knowledge-base");
    expect(buildObsidianUri("vault", "raw/llm-sim/park-2023.md")).toBe(
      "obsidian://open?vault=vault&file=raw%2Fllm-sim%2Fpark-2023.md",
    );
    // Reject parent traversal, encoded traversal, and Windows paths in file parameter
    expect(buildObsidianUri("vault", "../secret.md")).toBe("obsidian://open?vault=vault");
    expect(buildObsidianUri("vault", "raw/%2e%2e/secret.md")).toBe("obsidian://open?vault=vault");
    expect(buildObsidianUri("vault", "C:\\Users\\secret.md")).toBe("obsidian://open?vault=vault");

    // Duplicate citekey disambiguation + snapshotVaultLabel binding
    const dupPark: ResearchRecord = {
      id: "src-park-2",
      kind: "source",
      data: {
        title: "Generative Agents Follow-up Benchmark",
        authors: ["Joon Sung Park"],
        year: "2023",
        category: "llm-agents",
        reading_scope: "abstract",
        locator: "https://example.org/park-2",
      },
    };

    const vaultNote: ResearchRecord = {
      id: "note-park",
      kind: "library-note",
      data: {
        title: "Vault Note: Generative Agents",
        authors: ["Joon Sung Park"],
        year: "2023",
        category: "llm-agents",
        reading_scope: "full-text",
        note_path: "raw/llm-sim/park-2023.md",
        locator: "https://doi.org/10.1145/3586183.3606763",
      },
    };

    render(
      <LiteratureLibrary
        sources={[initialSources[0], dupPark, vaultNote]}
        screenings={initialScreenings}
        workspace={mockWorkspace}
        snapshotVaultLabel="snapshot-kb"
        projectId="llm-social-sim"
        projectTitle="LLM Social Simulation"
        t={tEn}
        onScreen={vi.fn()}
        onPrepare={vi.fn()}
      />,
    );

    const citeBar = screen.getByRole("group", { name: tEn("citeQuickLabel") });
    await user.click(within(citeBar).getByRole("button", { name: tEn("citeCopyApa") }));
    expect(writeText).toHaveBeenLastCalledWith(expect.stringContaining("Park, J. S."));

    await user.click(within(citeBar).getByRole("button", { name: tEn("citeCopyKey") }));
    expect(writeText).toHaveBeenLastCalledWith("[@park2023generative]");

    // Select second Park 2023 Generative paper -> must copy disambiguated [@park2023generative_2]
    await user.click(within(screen.getByRole("table")).getByRole("button", { name: "Generative Agents Follow-up Benchmark" }));
    const citeBar2 = screen.getByRole("group", { name: tEn("citeQuickLabel") });
    await user.click(within(citeBar2).getByRole("button", { name: tEn("citeCopyKey") }));
    expect(writeText).toHaveBeenLastCalledWith("[@park2023generative_2]");

    // Select read-only Obsidian note -> must use snapshotVaultLabel ("snapshot-kb"), not workspace vault ("vault")
    await user.click(within(screen.getByRole("table")).getByRole("button", { name: "Vault Note: Generative Agents" }));
    const obsidianLink = screen.getByRole("link", { name: /Open in Obsidian/i });
    expect(obsidianLink).toHaveAttribute(
      "href",
      "obsidian://open?vault=snapshot-kb&file=raw%2Fllm-sim%2Fpark-2023.md",
    );
    expect(obsidianLink.getAttribute("href")).not.toContain("C:");

    // Open Export Modal -> Direct Export Files -> verify RIS, CSL-JSON, APA, .base, and Obsidian link
    await user.click(screen.getByRole("button", { name: tEn("handoffOpenButton") }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("tab", { name: tEn("handoffTabExport") }));

    expect(within(dialog).getByRole("button", { name: tEn("handoffDownloadBib") })).toBeEnabled();
    expect(within(dialog).getByRole("button", { name: tEn("handoffDownloadRis") })).toBeEnabled();
    expect(within(dialog).getByRole("button", { name: tEn("handoffDownloadCsl") })).toBeEnabled();
    expect(within(dialog).getByRole("button", { name: tEn("handoffDownloadBase") })).toBeEnabled();
    expect(within(dialog).getByRole("link", { name: /Open in Obsidian/i })).toHaveAttribute(
      "href",
      "obsidian://open?vault=vault",
    );

    await user.click(within(dialog).getByRole("button", { name: tEn("handoffCopyApa") }));
    expect(writeText).toHaveBeenLastCalledWith(expect.stringContaining("Park, J. S."));
  });

  it("renders Evidence claim-source cards with reading-scope caution KPIs and submits checkbox source_ids", async () => {
    const user = userEvent.setup();
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true, record: { id: "claim-new", kind: "claim", data: {} } }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    try {
      const detail: ProjectDetail = {
        ok: true,
        project: {
          id: "proj-1",
          title: "Multi-Topic Benchmark",
          archetype: "review",
          goal: "Evaluate evidence grounding.",
        },
        records: [
          ...initialSources.slice(0, 3),
          {
            id: "claim-1",
            kind: "claim",
            data: {
              text: "Memory-reflection streams sustain multi-day agent coherence.",
              source_ids: ["src-1"],
              uncertainty: "Tested primarily in sandboxed town environments.",
            },
          },
          {
            id: "claim-2",
            kind: "claim",
            data: {
              text: "Synthetic LLM survey panels understate human variance.",
              source_ids: ["src-3"],
              uncertainty: "Currently backed by abstract-only source; verify full text.",
            },
          },
          {
            id: "claim-3",
            kind: "claim",
            data: {
              text: "Unlinked working hypothesis awaiting literature binding.",
              source_ids: [],
              uncertainty: "No source linked yet.",
            },
          },
        ],
        artifacts: [],
        tasks: [],
        actions: [],
        manuscript: null,
        workflow: null,
        warnings: [],
      };

      const onSaved = vi.fn().mockResolvedValue(undefined);
      function StatefulPagesHarness() {
        const [activePage, setActivePage] = useState<"evidence" | "literature" | "overview" | "design" | "manuscript" | "review">("evidence");
        return (
          <ProjectPages
            detail={detail}
            workspace={mockWorkspace}
            page={activePage}
            t={tEn}
            onSaved={onSaved}
            navigate={(nextPage) => setActivePage(nextPage)}
          />
        );
      }
      render(<StatefulPagesHarness />);

      // KPI checks: 3 claims total, 2 linked, 1 abstract-only caution, 1 unlinked
      expect(screen.getByText(tEn("evidenceTotalClaims")).nextElementSibling).toHaveTextContent("3");
      expect(screen.getByText(tEn("evidenceSupportedClaims")).nextElementSibling).toHaveTextContent("2");
      expect(screen.getByText(tEn("evidenceAbstractCaution")).nextElementSibling).toHaveTextContent("1");
      expect(screen.getByText(tEn("evidenceUnsupportedClaims")).nextElementSibling).toHaveTextContent("1");

      // Submit a new claim selecting 2 sources via 1-click checkboxes
      const addPanel = screen.getByRole("heading", { name: tEn("addClaim") }).closest("section")!;
      fireEvent.change(within(addPanel).getByLabelText(new RegExp(`^${tEn("claim")}`)), {
        target: { value: "Coupled hydro-agent models improve drought equity." },
      });
      fireEvent.change(within(addPanel).getByLabelText(new RegExp(`^${tEn("uncertainty")}`)), {
        target: { value: "Requires multi-basin validation." },
      });

      const checkboxes = within(addPanel).getAllByRole("checkbox");
      expect(checkboxes).toHaveLength(3);
      await user.click(checkboxes[0]);
      await user.click(checkboxes[1]);
      await user.click(within(addPanel).getByRole("button", { name: tEn("addClaim") }));

      expect(fetchSpy).toHaveBeenCalledTimes(1);
      const [, reqInit] = fetchSpy.mock.calls[0];
      const sentBody = JSON.parse(String(reqInit?.body));
      expect(sentBody).toEqual({
        kind: "claim",
        data: {
          text: "Coupled hydro-agent models improve drought equity.",
          source_ids: ["src-1", "src-2"],
          uncertainty: "Requires multi-basin validation.",
        },
      });
      expect(onSaved).toHaveBeenCalledTimes(1);

      // Clicking "Open in Reader" on Claim #2 (src-3) switches to Literature and selects src-3 in Reader Desk!
      const openReaderBtns = screen.getAllByRole("button", { name: tEn("evidenceJumpToPaper") });
      await user.click(openReaderBtns[1]);
      const detailPane = screen.getByRole("complementary", { name: tEn("catalogDetail") });
      expect(within(detailPane).getByRole("heading", { name: /Synthetic Replacements for Human Survey Data/ })).toBeVisible();
    } finally {
      fetchSpy.mockRestore();
    }
  });
});
