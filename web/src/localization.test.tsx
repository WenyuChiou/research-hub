import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { Readiness } from "./Pages";
import { statusLabel, translator } from "./i18n";
import type { ProjectDetail, Workspace } from "./types";

const writingWarning =
  "Bind the public writing adapter to initialize manuscript authority; no manuscript checks have passed yet.";
const translatedWarning =
  "請連結公開寫作介接器，建立稿件的正式狀態來源；目前尚無任何稿件檢查通過。";
const unknownWarning =
  "Manuscript authority needs review: adapter fingerprint changed";
const detail: ProjectDetail = {
  ok: true,
  project: {
    id: "localization",
    title: "Localization fixture",
    archetype: "empirical",
    goal: "UI presentation only.",
  },
  records: [],
  artifacts: [],
  tasks: [],
  actions: [],
  manuscript: null,
  workflow: null,
  warnings: [
    writingWarning,
    unknownWarning,
    `${writingWarning} Diagnostic detail.`,
  ],
};
const workspace: Workspace = {
  ok: true,
  projects: [detail.project],
  capabilities: {
    codex: {
      status: "unavailable",
      message: "Synthetic capability timeout; no live execution verified.",
    },
    writing: {
      status: "unavailable",
      message: "Synthetic adapter check failed: fingerprint differs.",
    },
    approval: {
      status: "unavailable",
      message: "Synthetic approval session absent.",
    },
  },
  protection_scope: "Synthetic scope; no data or connectors.",
};
const response = (value: unknown) => new Response(JSON.stringify(value));
afterEach(() => vi.unstubAllGlobals());

describe("localized readiness and writing-authority warning", () => {
  it("translates all three unavailable summaries without changing their diagnostic messages", () => {
    render(<Readiness workspace={workspace} t={translator("zh-TW")} />);
    expect(
      screen.getAllByText("目前無法使用", { selector: ".capability-status" }),
    ).toHaveLength(3);
    expect(screen.queryByText("unavailable")).not.toBeInTheDocument();
    [
      workspace.capabilities.codex,
      workspace.capabilities.writing,
      workspace.capabilities.approval,
    ].forEach((capability) => {
      expect(screen.getByText(capability.message)).toBeInTheDocument();
      expect(capability.status).toBe("unavailable");
    });
  });

  it("preserves English status strings, unknown statuses, and task acceptance semantics", () => {
    const en = translator("en");
    const zh = translator("zh-TW");
    expect(statusLabel("unavailable", en)).toBe("unavailable");
    expect(statusLabel("available", en)).toBe("available");
    expect(statusLabel("available", zh)).toBe("可使用");
    expect(statusLabel("future_capability_status", zh)).toBe(
      "future_capability_status",
    );
    expect(statusLabel("completed", en)).toBe("Accepted by human");
    expect(statusLabel("completed", zh)).toBe("人工已接受");
  });

  it("translates only the exact known warning on locale switches, retaining unknown diagnostic details", async () => {
    const user = userEvent.setup();
    const original = JSON.stringify({ workspace, detail });
    const fetch = vi.fn(async (url: string) =>
      response(url.endsWith("/workspace") ? workspace : detail),
    );
    vi.stubGlobal("fetch", fetch);
    render(<App />);
    await screen.findByText(writingWarning, { exact: true });
    const sidebar = screen
      .getByText("EN", { selector: "button" })
      .closest("aside");
    const languages = within(
      within(sidebar!).getByRole("group", { name: "Interface language" }),
    );
    await user.click(languages.getByRole("button", { name: "繁體中文" }));
    expect(
      screen.getByText(translatedWarning, { exact: true }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(writingWarning, { exact: true }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(unknownWarning, { exact: true }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(`${writingWarning} Diagnostic detail.`, { exact: true }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText("目前無法使用", { selector: ".capability-status" }),
    ).toHaveLength(6);
    await user.click(languages.getByRole("button", { name: "EN" }));
    expect(
      screen.getByText(writingWarning, { exact: true }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(translatedWarning, { exact: true }),
    ).not.toBeInTheDocument();
    expect(
      screen.getAllByText("unavailable", { selector: ".capability-status" }),
    ).toHaveLength(6);
    expect(JSON.stringify({ workspace, detail })).toBe(original);
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
