import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import type { ProjectDetail, Workspace } from "./types";

const projectOne = {
  id: "hydro-agents",
  title: "Hydrology Multi-Agent Synthesis",
  archetype: "review" as const,
  goal: "Evaluate coupled LLM-hydrological simulation validity.",
};

const projectTwo = {
  id: "clinical-triage",
  title: "Clinical Triage Benchmark",
  archetype: "empirical" as const,
  goal: "Measure bedside alert precision.",
};

const workspaceFixture: Workspace = {
  ok: true,
  projects: [projectOne, projectTwo],
  protection_scope: "Local workspace boundary",
  capabilities: {
    codex: { status: "available", message: "Codex ready" },
    writing: { status: "unavailable", message: "Writing adapter optional" },
    approval: { status: "available", message: "Human review active" },
    local_integrations: {
      version: 1,
      status: "available",
      zotero_configured: true,
      nlm_state_present: true,
      obsidian_vault_configured: true,
      obsidian_vault_name: "ResearchVault",
    },
  },
};

const detailOne: ProjectDetail = {
  ok: true,
  project: projectOne,
  records: [
    {
      id: "src-2023",
      kind: "source",
      data: {
        title: "Generative Agents: Interactive Simulacra",
        authors: ["Joon Sung Park"],
        year: "2023",
        category: "llm",
        tags: ["multi-agent", "memory"],
        reading_scope: "full-text",
        doi: "10.1145/3586183.3606763",
        locator: "https://doi.org/10.1145/3586183.3606763",
        summary: "Memory stream architecture for social agents.",
        identity_status: "unverified",
      },
    },
    {
      id: "src-2024",
      kind: "source",
      data: {
        title: "Watershed Coupled Reservoir Agents",
        authors: ["Lin Wei", "Hao Du"],
        year: "2024",
        category: "human",
        tags: ["hydrology", "multi-agent"],
        reading_scope: "abstract",
        doi: "10.1029/2024WR037001",
        locator: "https://doi.org/10.1029/2024WR037001",
        abstract: "Abstract-level evaluation of basin allocation rules.",
        identity_status: "unverified",
      },
    },
    {
      id: "scr-2023",
      kind: "screening",
      data: {
        source_id: "src-2023",
        decision: "include",
        rationale: "Foundational full-text baseline.",
      },
    },
    {
      id: "scr-2024",
      kind: "screening",
      data: {
        source_id: "src-2024",
        decision: "include",
        rationale: "Core 2024 watershed comparator.",
      },
    },
    {
      id: "claim-1",
      kind: "claim",
      data: {
        text: "Basin allocation agents adapt reservoir release schedules under drought.",
        source_ids: ["src-2024"],
        uncertainty: "Currently backed by abstract-only source.",
        verification_status: "unverified",
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

const detailTwo: ProjectDetail = {
  ok: true,
  project: projectTwo,
  records: [],
  artifacts: [],
  tasks: [],
  actions: [],
  manuscript: null,
  workflow: null,
  warnings: [],
};

function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
  window.history.replaceState({}, "", "#literature");
  delete document.documentElement.dataset.theme;
  delete document.documentElement.dataset.themeMode;
});

describe("Integrated Workstation: Theme, Settings SyncSlot, Visual Overview, Matrix & Ctrl+K", () => {
  it("keeps localStorage clean on mount, toggles Dark Mode, wires SyncHooksPanel into Settings & Handoff Modal, filters Literature from Overview year chart, renders Matrix view, and jumps via Ctrl+K", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/workspace")) return jsonResponse(workspaceFixture);
        if (url.includes("/projects/clinical-triage")) return jsonResponse(detailTwo);
        return jsonResponse(detailOne);
      }),
    );

    window.history.replaceState({}, "", "#overview");
    render(<App />);

    // Wait for project detail to load on Overview
    expect(await screen.findByText(projectOne.goal)).toBeVisible();

    // 1. Zero initial localStorage writes; deterministic light default
    expect(window.localStorage.length).toBe(0);
    expect(document.documentElement.dataset.theme).toBe("light");

    // 2. Toggle Dark Mode from sidebar ThemeQuickButton
    await user.click(screen.getByRole("button", { name: /Switch to dark theme/i }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem("research-hub-theme")).toBe("dark");

    // 3. Open Settings Center -> verify syncSlot is wired & visible immediately on open, then switch locale in Appearance
    await user.click(screen.getByRole("button", { name: "Setup" }));
    const settingsDialog = screen.getByRole("dialog", { name: "Setup" });
    expect(within(settingsDialog).getByText(/Quick Sync to Connected Apps/i)).toBeVisible();
    expect(within(settingsDialog).getByText("Overleaf .bib")).toBeVisible();

    await user.click(within(settingsDialog).getByRole("tab", { name: /Appearance/i }));
    await user.click(within(settingsDialog).getByRole("radio", { name: /繁體中文/ }));
    expect(document.documentElement.lang).toBe("zh-TW");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "設定" })).not.toBeInTheDocument();

    // 4. Overview renders ResearchStageStepper, EvidenceBlindSpotRadar, and LiteratureVisualCharts
    expect(screen.getByRole("heading", { name: "證據風險與研究盲點雷達" })).toBeVisible();
    const year2024Bar = screen.getByRole("button", { name: /2024 年：共 1 篇/ });
    await user.click(year2024Bar);

    // Clicking the 2024 year bar navigates to Literature filtered to 2024 (1 matching paper)
    expect(await screen.findByRole("heading", { level: 1, name: "文獻" })).toBeVisible();
    expect(screen.getByLabelText("依年份篩選")).toHaveValue("2024");
    const readerDesk = screen.getByRole("complementary", { name: "所選文獻" });
    expect(within(readerDesk).getByRole("heading", { name: "Watershed Coupled Reservoir Agents" })).toBeVisible();

    // Clear filters -> both papers visible; switch to 3rd view mode: Matrix (矩陣)
    await user.click(screen.getByRole("button", { name: "清除" }));
    await user.click(screen.getByRole("button", { name: "矩陣" }));
    const matrixRegion = screen.getByRole("region", { name: "文獻 × 主題標籤與證據交叉矩陣" });
    expect(within(matrixRegion).getByText("證據已引用 1/2 篇")).toBeVisible();

    // Clicking a paper in SynthesisMatrix opens it in Split Reader Desk
    await user.click(within(matrixRegion).getByRole("button", { name: /Generative Agents: Interactive Simulacra/ }));
    expect(within(readerDesk).getByRole("heading", { name: "Generative Agents: Interactive Simulacra" })).toHaveFocus();

    // 5. Open AgentHandoffModal -> switch to Connected Sync (同步至軟體) tab
    await user.click(screen.getByRole("button", { name: "AI 助理與匯出" }));
    const handoffDialog = screen.getByRole("dialog", { name: "AI 助理交接與檔案匯出" });
    await user.click(within(handoffDialog).getByRole("tab", { name: "同步至軟體" }));
    expect(within(handoffDialog).getByRole("button", { name: "產生 NLM 匯入包" })).toBeEnabled();
    expect(within(handoffDialog).getByRole("button", { name: "預覽同步 (Dry-run)" })).toBeEnabled();
    await user.keyboard("{Escape}");

    // 6. Global Ctrl+K Command Palette -> search paper & press Enter to open it in Reader Desk
    await user.click(screen.getByRole("link", { name: "證據" }));
    expect(await screen.findByRole("heading", { level: 1, name: "證據" })).toBeVisible();
    // Compact Blind-Spot Radar is also surfaced on Evidence page
    expect(screen.getByRole("heading", { name: "證據風險與研究盲點雷達" })).toBeVisible();

    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const cmdDialog = screen.getByRole("dialog", { name: "全域指令面板" });
    const cmdInput = within(cmdDialog).getByRole("textbox", { name: "全域指令面板" });
    await user.type(cmdInput, "Watershed");
    await user.keyboard("{Enter}");

    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "全域指令面板" })).not.toBeInTheDocument();
    });
    const litReaderDesk = await screen.findByRole("complementary", { name: "所選文獻" });
    expect(within(litReaderDesk).getByRole("heading", { name: "Watershed Coupled Reservoir Agents" })).toBeVisible();
  }, 20000);
});
