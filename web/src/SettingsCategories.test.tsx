import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import {
  IntegrationsSetup,
  type SettingsThemeMode,
} from "./IntegrationsSetup";
import { translator } from "./i18n";
import type { Locale, Workspace } from "./types";

vi.mock("./api", () => ({
  api: vi.fn(() => new Promise(() => {})),
  recoverCsrfIfForbidden: vi.fn(async () => false),
  refreshSessionTokens: vi.fn(async () => true),
  ApiError: class ApiError extends Error {
    status = 500;
    code = "error";
  },
  segment: encodeURIComponent,
}));

afterEach(cleanup);

const sampleWorkspace: Workspace = {
  ok: true,
  projects: [],
  protection_scope: "local",
  setup_snapshot: {
    schema_version: 1,
    source: "saved_local_setup_snapshot",
    current_status: "unknown",
    freshness: "saved",
    observed_at: "2026-11-20T08:30:00Z",
    age_seconds: 120,
    display_max_age_seconds: 86400,
    components: {
      environment: "passed",
      vault: "passed",
      zotero: "failed",
      notebooklm_auth: "skipped",
      llm_cli: "passed",
      skills: "unknown",
    },
  },
  capabilities: {
    codex: { status: "available", message: "Connected Codex CLI ready" },
    writing: { status: "available", message: "Scientific writing adapter bound" },
    approval: { status: "available", message: "Local operator session enabled" },
    obsidian_validation: {
      version: 1,
      status: "available",
      read_only: true,
      scope: "startup_selected_exact_vault",
      authorized_vault: "/synthetic/research-vault",
    },
    local_integrations: {
      version: 1,
      status: "available",
      zotero_configured: true,
      zotero_api_key_present: true,
      zotero_api_key_encrypted: true,
      zotero_library_id: "445566",
      zotero_library_type: "user",
      nlm_state_present: true,
      obsidian_cli_present: true,
      obsidian_vault_configured: true,
      obsidian_vault_name: "research-vault",
    },
  },
};

function assertAllLinksSafe(container: HTMLElement) {
  const anchors = Array.from(container.querySelectorAll("a"));
  for (const anchor of anchors) {
    expect(anchor.rel).toBe("noopener noreferrer");
  }
}

describe("Categorized Modern Settings Center", () => {
  it("switches cleanly across Connections, Appearance, AI & Review, and Diagnostics while keeping all links safe", async () => {
    const user = userEvent.setup();
    const t = translator("en");
    render(<IntegrationsSetup workspace={sampleWorkspace} t={t} />);

    await user.click(screen.getByRole("button", { name: t("integrationsSetup") }));
    const dialog = screen.getByRole("dialog");

    // 1. Default category: Connections & Sync
    const connectionsTab = within(dialog).getByRole("tab", {
      name: /Connections & Sync/i,
    });
    expect(connectionsTab).toHaveAttribute("aria-selected", "true");
    expect(
      within(dialog).getByRole("heading", { name: "Obsidian" }),
    ).toBeVisible();
    expect(
      within(dialog).getByRole("heading", { name: "Zotero" }),
    ).toBeVisible();
    expect(
      within(dialog).getByRole("heading", { name: "NotebookLM" }),
    ).toBeVisible();
    expect(dialog.querySelectorAll(".settings-led-pill")).toHaveLength(3);
    assertAllLinksSafe(dialog);

    // Verify obsidian:// deep link also carries rel="noopener noreferrer"
    const obsidianLink = Array.from(dialog.querySelectorAll("a")).find((a) =>
      a.getAttribute("href")?.startsWith("obsidian://"),
    );
    expect(obsidianLink).toBeDefined();
    expect(obsidianLink?.rel).toBe("noopener noreferrer");

    // 2. Category 2: Appearance & Language
    await user.click(
      within(dialog).getByRole("tab", { name: /Appearance & Language/i }),
    );
    expect(
      within(dialog).getByRole("radiogroup", { name: /Theme Mode/i }),
    ).toBeVisible();
    expect(
      within(dialog).getByRole("radiogroup", { name: t("language") }),
    ).toBeVisible();
    assertAllLinksSafe(dialog);

    // 3. Category 3: AI & Review Gate
    await user.click(
      within(dialog).getByRole("tab", { name: /AI & Review Gate/i }),
    );
    expect(within(dialog).getByText("Codex Runner")).toBeVisible();
    expect(within(dialog).getByText("Writing Adapter")).toBeVisible();
    expect(within(dialog).getByText("Human Approval Gate")).toBeVisible();
    expect(within(dialog).getByText("Obsidian CLI (v1.12+)")).toBeVisible();
    assertAllLinksSafe(dialog);

    // 4. Category 4: Diagnostics & Privacy (6-tile health matrix + security badges)
    await user.click(
      within(dialog).getByRole("tab", { name: /Diagnostics & Privacy/i }),
    );
    expect(within(dialog).getByText("Loopback CSRF")).toBeVisible();
    expect(within(dialog).getByText("AES-GCM (0600)")).toBeVisible();
    expect(within(dialog).getByText("Read-Only Vault")).toBeVisible();
    expect(within(dialog).getByText(t("snapshotEnvironment"))).toBeVisible();
    expect(within(dialog).getByText(t("snapshotVault"))).toBeVisible();
    expect(within(dialog).getByText(t("snapshotZotero"))).toBeVisible();
    expect(within(dialog).getByText(t("snapshotNlm"))).toBeVisible();
    expect(within(dialog).getByText(t("snapshotCli"))).toBeVisible();
    expect(within(dialog).getByText(t("snapshotSkills"))).toBeVisible();
    expect(within(dialog).getByText("2026-11-20T08:30:00Z")).toHaveAttribute(
      "datetime",
      "2026-11-20T08:30:00Z",
    );
    assertAllLinksSafe(dialog);
  });

  it("toggles Light / Dark / System theme radio cards and Traditional Chinese / English language cards without initial storage writes", async () => {
    const user = userEvent.setup();
    const storageSpy = vi.spyOn(Storage.prototype, "setItem");
    const themeChanges: SettingsThemeMode[] = [];
    const localeChanges: Locale[] = [];

    function Harness() {
      const [mode, setMode] = useState<SettingsThemeMode>("light");
      const [loc, setLoc] = useState<Locale>("en");
      const tr = translator(loc);
      return (
        <IntegrationsSetup
          workspace={sampleWorkspace}
          t={tr}
          themeMode={mode}
          onThemeModeChange={(next) => {
            themeChanges.push(next);
            setMode(next);
          }}
          locale={loc}
          onLocaleChange={(next) => {
            localeChanges.push(next);
            setLoc(next);
          }}
        />
      );
    }

    render(<Harness />);
    expect(storageSpy).not.toHaveBeenCalled();

    await user.click(
      screen.getByRole("button", { name: translator("en")("integrationsSetup") }),
    );
    const dialog = screen.getByRole("dialog");

    await user.click(
      within(dialog).getByRole("tab", { name: /Appearance & Language/i }),
    );

    const lightRadio = within(dialog).getByRole("radio", { name: /Light/i });
    const darkRadio = within(dialog).getByRole("radio", { name: /Dark/i });
    const systemRadio = within(dialog).getByRole("radio", { name: /System/i });

    expect(lightRadio).toHaveAttribute("aria-checked", "true");
    expect(darkRadio).toHaveAttribute("aria-checked", "false");

    await user.click(darkRadio);
    expect(themeChanges).toEqual(["dark"]);
    expect(darkRadio).toHaveAttribute("aria-checked", "true");
    expect(lightRadio).toHaveAttribute("aria-checked", "false");

    await user.click(systemRadio);
    expect(themeChanges).toEqual(["dark", "system"]);
    expect(systemRadio).toHaveAttribute("aria-checked", "true");

    // Toggle language to zh-TW and verify live bilingual switch
    const zhRadio = within(dialog).getByRole("radio", { name: /繁體中文/ });
    await user.click(zhRadio);
    expect(localeChanges).toEqual(["zh-TW"]);
    expect(zhRadio).toHaveAttribute("aria-checked", "true");
    expect(
      within(dialog).getByRole("tab", { name: /連線與同步/ }),
    ).toBeVisible();
    expect(
      within(dialog).getByRole("tab", { name: /外觀與語言/ }),
    ).toHaveAttribute("aria-selected", "true");

    const enRadio = within(dialog).getByRole("radio", { name: /English/i });
    await user.click(enRadio);
    expect(localeChanges).toEqual(["zh-TW", "en"]);
    expect(enRadio).toHaveAttribute("aria-checked", "true");

    storageSpy.mockRestore();
  });

  it("renders optional syncSlot inside the collapsible Quick Sync drawer on Connections", async () => {
    const user = userEvent.setup();
    const tr = translator("zh-TW");
    render(
      <IntegrationsSetup
        workspace={sampleWorkspace}
        locale="zh-TW"
        t={tr}
        syncSlot={
          <div data-testid="mock-sync-slot">
            <span>Connected Sync Controls</span>
            <a
              href="https://notebooklm.google.com/"
              target="_blank"
              rel="noopener noreferrer"
            >
              Open NLM
            </a>
          </div>
        }
      />,
    );

    await user.click(
      screen.getByRole("button", { name: tr("integrationsSetup") }),
    );
    const dialog = screen.getByRole("dialog");

    expect(
      within(dialog).getByText("一鍵匯入與同步至已連接軟體"),
    ).toBeVisible();
    expect(within(dialog).getByTestId("mock-sync-slot")).toBeVisible();
    assertAllLinksSafe(dialog);
  });

  it("supports keyboard ArrowDown / ArrowUp navigation across the category rail", async () => {
    const user = userEvent.setup();
    const t = translator("en");
    render(<IntegrationsSetup workspace={sampleWorkspace} t={t} />);

    await user.click(screen.getByRole("button", { name: t("integrationsSetup") }));
    const dialog = screen.getByRole("dialog");

    const connectionsTab = within(dialog).getByRole("tab", {
      name: /Connections & Sync/i,
    });
    connectionsTab.focus();
    await user.keyboard("{ArrowDown}");

    const appearanceTab = within(dialog).getByRole("tab", {
      name: /Appearance & Language/i,
    });
    expect(appearanceTab).toHaveFocus();
    expect(appearanceTab).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{End}");
    const privacyTab = within(dialog).getByRole("tab", {
      name: /Diagnostics & Privacy/i,
    });
    expect(privacyTab).toHaveFocus();
    expect(privacyTab).toHaveAttribute("aria-selected", "true");
  });
});
