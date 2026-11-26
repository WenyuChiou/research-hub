import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SyncHooksPanel } from "./SyncHooksBar";
import type { ResearchRecord, Workspace } from "./types";

const SAMPLE_SOURCES: ResearchRecord[] = [
  {
    id: "src-1",
    kind: "source",
    data: {
      title: "Agentic Watershed Simulation",
      locator: "https://doi.org/10.1029/2025WR000001",
      doi: "10.1029/2025WR000001",
      authors: ["Lin, Mei-Hua", "Chen, Wei"],
      year: "2025",
      venue: "Water Resources Research",
      reading_scope: "full-text",
      tags: ["hydrology", "agent"],
      summary: "Full-text simulation benchmark.",
    },
  },
  {
    id: "src-2",
    kind: "source",
    data: {
      title: "LLM Benchmark Drift Survey",
      locator: "https://arxiv.org/abs/2409.12345",
      doi: "10.48550/arXiv.2409.12345",
      authors: ["Patel, Aria"],
      year: "2024",
      reading_scope: "abstract",
      tags: ["benchmark"],
      summary: "Abstract-only survey.",
    },
  },
];

const ENABLED_WORKSPACE: Workspace = {
  ok: true,
  projects: [{ id: "proj-1", title: "Hydrology Agents", archetype: "review", goal: "Review" }],
  capabilities: {
    local_integrations: {
      version: 1,
      status: "available",
      zotero_configured: true,
      nlm_state_present: true,
      obsidian_vault_configured: true,
      obsidian_vault_name: "ResearchVault",
    },
    codex: { status: "available", message: "ok" },
    writing: { status: "available", message: "ok" },
    approval: { status: "available", message: "ok" },
  },
  protection_scope: "test",
};

describe("SyncHooksPanel", () => {
  beforeEach(() => {
    let csrfMeta = document.querySelector<HTMLMetaElement>('meta[name="research-hub-csrf-token"]');
    if (!csrfMeta) {
      csrfMeta = document.createElement("meta");
      csrfMeta.name = "research-hub-csrf-token";
      document.head.appendChild(csrfMeta);
    }
    csrfMeta.content = "test-csrf-token";
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders all 4 connected destinations with zero fetch on mount and safe rel attributes", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const { container } = render(
      <SyncHooksPanel
        projectId="proj-1"
        projectTitle="Hydrology Agents"
        sources={SAMPLE_SOURCES}
        workspace={ENABLED_WORKSPACE}
        locale="zh-TW"
      />,
    );

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(screen.getByText("NotebookLM")).toBeTruthy();
    expect(screen.getByText("Zotero")).toBeTruthy();
    expect(screen.getByText("Obsidian")).toBeTruthy();
    expect(screen.getByText("Overleaf .bib")).toBeTruthy();
    expect(screen.getByText("EndNote .ris")).toBeTruthy();
    expect(screen.getByText("Quarto CSL-JSON")).toBeTruthy();
    expect(screen.getByText("APA 7th")).toBeTruthy();

    const links = Array.from(container.querySelectorAll("a"));
    expect(links.length).toBeGreaterThanOrEqual(2);
    for (const link of links) {
      expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    }
    const obsidianLink = screen.getByRole("link", { name: /在 Obsidian 開啟/ });
    expect(obsidianLink.getAttribute("href")).toBe("obsidian://open?vault=ResearchVault");
  });

  it("bundles NotebookLM pack on click and displays visual receipt", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          ok: true,
          export_dir: ".research/exports/notebooklm-proj-1",
          pack_file: ".research/exports/notebooklm-proj-1/00-notebooklm-source-pack.md",
          source_count: 2,
          full_text_count: 1,
          abstract_or_metadata_count: 1,
          nlm_status: "authenticated",
          notebook_url: "https://notebooklm.google.com/",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    render(
      <SyncHooksPanel
        projectId="proj-1"
        projectTitle="Hydrology Agents"
        sources={SAMPLE_SOURCES}
        selectedIds={["src-1", "src-2"]}
        workspace={ENABLED_WORKSPACE}
        locale="zh-TW"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "產生 NLM 匯入包" }));

    await waitFor(() => {
      expect(screen.getByText(/✓ 2 篇已封裝 · 全文 1 \/ 摘要 1/)).toBeTruthy();
    });
    expect(screen.getByText(".research/exports/notebooklm-proj-1")).toBeTruthy();
    expect(screen.getByText("已登入")).toBeTruthy();

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [calledUrl, calledInit] = fetchSpy.mock.calls[0];
    expect(calledUrl).toBe("/api/v1/projects/proj-1/integrations/notebooklm/bundle");
    expect(JSON.parse(String(calledInit?.body))).toEqual({
      selected_source_ids: ["src-1", "src-2"],
    });
  });

  it("executes 2-step Zotero dry-run preview -> confirm write flow", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ok: true,
            status: "ready",
            dry_run: true,
            candidate_count: 2,
            would_create: 1,
            duplicates: 1,
            items: [
              { id: "src-1", title: "Agentic Watershed Simulation", doi: "10.1029/2025WR000001", action: "create" },
              { id: "src-2", title: "LLM Benchmark Drift Survey", doi: "10.48550/arXiv.2409.12345", action: "skip_duplicate" },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ok: true,
            status: "synced",
            dry_run: false,
            created_count: 1,
            skipped_duplicates: 1,
            created_keys: ["ZKEY01"],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );

    render(
      <SyncHooksPanel
        projectId="proj-1"
        projectTitle="Hydrology Agents"
        sources={SAMPLE_SOURCES}
        workspace={ENABLED_WORKSPACE}
        locale="zh-TW"
      />,
    );

    // Step 1: Dry-run preview
    fireEvent.click(screen.getByRole("button", { name: "預覽同步 (Dry-run)" }));

    await waitFor(() => {
      expect(screen.getByText("新增 1 篇 · 略過重複 1 篇")).toBeTruthy();
    });

    const confirmBtn = screen.getByRole("button", { name: "確認寫入 Zotero" });
    expect(confirmBtn).toBeTruthy();

    // Step 2: Confirm live write
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(screen.getByText(/✓ 已同步 1 篇至 Zotero/)).toBeTruthy();
    });

    expect(fetchSpy).toHaveBeenCalledTimes(2);
    expect(JSON.parse(String(fetchSpy.mock.calls[0][1]?.body))).toEqual({ dry_run: true });
    expect(JSON.parse(String(fetchSpy.mock.calls[1][1]?.body))).toEqual({ dry_run: false });
  });

  it("generates Obsidian notes & .base pack and supports English locale", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          ok: true,
          export_dir: ".research/exports/obsidian-proj-1",
          base_file: ".research/exports/obsidian-proj-1/proj-1.base",
          note_count: 2,
          obsidian_vault_name: "HydroVault",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    render(
      <SyncHooksPanel
        projectId="proj-1"
        projectTitle="Hydrology Agents"
        sources={SAMPLE_SOURCES}
        workspace={ENABLED_WORKSPACE}
        locale="en"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Generate Notes & .base" }));

    await waitFor(() => {
      expect(screen.getByText("✓ 2 note(s) + .base ready")).toBeTruthy();
    });
    expect(screen.getByText(".research/exports/obsidian-proj-1")).toBeTruthy();
    const openLink = screen.getByRole("link", { name: /Open in Obsidian/ });
    expect(openLink.getAttribute("href")).toBe("obsidian://open?vault=HydroVault");
  });

  it("discards stale Zotero dry-run preview when selection changes in flight and surfaces failed writes", async () => {
    let resolvePreview!: (res: Response) => void;
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            resolvePreview = resolve;
          }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ok: true,
            status: "ready",
            dry_run: true,
            candidate_count: 2,
            would_create: 2,
            duplicates: 0,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ok: true,
            status: "failed",
            dry_run: false,
            created_count: 0,
            failed_count: 2,
            created_keys: [],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );

    const { rerender } = render(
      <SyncHooksPanel
        projectId="proj-1"
        projectTitle="Hydrology Agents"
        sources={SAMPLE_SOURCES}
        selectedIds={["src-1"]}
        workspace={ENABLED_WORKSPACE}
        locale="en"
      />,
    );

    // Start preview for src-1, then switch scope to project-wide before it resolves
    fireEvent.click(screen.getByRole("button", { name: "Preview Sync (Dry-run)" }));
    rerender(
      <SyncHooksPanel
        projectId="proj-1"
        projectTitle="Hydrology Agents"
        sources={SAMPLE_SOURCES}
        workspace={ENABLED_WORKSPACE}
        locale="en"
      />,
    );

    resolvePreview(
      new Response(
        JSON.stringify({
          ok: true,
          status: "ready",
          dry_run: true,
          candidate_count: 1,
          would_create: 1,
          duplicates: 0,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Confirm Write to Zotero" })).toBeNull();
    });

    // Fresh preview on new selection succeeds, then rejected write reports failure instead of success
    fireEvent.click(screen.getByRole("button", { name: "Preview Sync (Dry-run)" }));
    const confirmBtn = await screen.findByRole("button", { name: "Confirm Write to Zotero" });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toMatch(/Zotero write failed/);
    });
    expect(screen.queryByText(/✓ Synced/)).toBeNull();
    expect(fetchSpy).toHaveBeenCalledTimes(3);
  });
});
