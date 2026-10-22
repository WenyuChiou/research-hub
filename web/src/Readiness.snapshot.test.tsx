import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Readiness } from "./Pages";
import { translator } from "./i18n";
import type { SetupSnapshot, Workspace } from "./types";

const base: Workspace = {
  ok: true,
  projects: [],
  protection_scope: "Existing protection boundary",
  capabilities: {
    codex: { status: "unavailable", message: "Codex unchanged" },
    writing: { status: "available", message: "Writing unchanged" },
    approval: { status: "unavailable", message: "Approval unchanged" },
  },
};
const saved: SetupSnapshot = {
  schema_version: 1,
  source: "saved_local_setup_snapshot",
  current_status: "unknown",
  freshness: "saved",
  observed_at: "2026-10-22T12:00:00Z",
  age_seconds: 12,
  display_max_age_seconds: 86400,
  components: {
    environment: "passed",
    vault: "failed",
    zotero: "skipped",
    notebooklm_auth: "unknown",
    llm_cli: "unknown",
    skills: "unknown",
  },
};

describe("saved setup observations", () => {
  it.each(["en", "zh-TW"] as const)(
    "keeps setup and protection summaries as native disclosure controls in %s",
    async (locale) => {
      const user = userEvent.setup();
      const t = translator(locale);
      const { container } = render(
        <Readiness workspace={{ ...base, setup_snapshot: saved }} t={t} />,
      );
      const summaries = Array.from(
        container.querySelectorAll<HTMLElement>("details.protection > summary"),
      );
      expect(summaries.map((summary) => summary.textContent)).toEqual([
        `${t("setupSnapshot")}: ${t("snapshotSaved")}`,
        t("protection"),
      ]);
      for (const summary of summaries) {
        const disclosure = summary.parentElement as HTMLDetailsElement;
        expect(disclosure.firstElementChild).toBe(summary);
        expect(summary).not.toHaveAttribute("role");
        expect(summary).not.toHaveAttribute("tabindex");
        expect(
          summary.querySelector(
            'button, a[href], input, select, textarea, [role="button"], [tabindex]',
          ),
        ).toBeNull();
        expect(disclosure.open).toBe(false);
        await user.click(summary);
        expect(disclosure.open).toBe(true);
        await user.click(summary);
        expect(disclosure.open).toBe(false);
      }
    },
  );
  it("supports older responses without making a probe or readiness claim", () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    render(<Readiness workspace={base} t={translator("en")} />);
    expect(screen.getByText(/No saved snapshot/)).toBeInTheDocument();
    expect(
      screen.getByText(/Current readiness remains unknown/),
    ).toBeInTheDocument();
    expect(screen.getByText("Codex unchanged")).toBeInTheDocument();
    expect(screen.getByText("Writing unchanged")).toBeInTheDocument();
    expect(screen.getByText("Approval unchanged")).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
    fetch.mockRestore();
  });
  it("labels timestamp, historical results and display policy without raw payload", () => {
    render(
      <Readiness
        workspace={{ ...base, setup_snapshot: saved }}
        t={translator("en")}
      />,
    );
    expect(
      screen.getByText(/Historical observations only/),
    ).toBeInTheDocument();
    expect(screen.getByText("2026-10-22T12:00:00Z")).toBeInTheDocument();
    expect(
      screen.getByText(
        /Required environment presence: Reported pass \(historical\)/,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Vault filesystem checks: Reported failure \(historical\)/,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/not a capability validity guarantee/),
    ).toHaveTextContent("86400");
    expect(
      screen.getByText(/That command may probe Zotero/),
    ).toBeInTheDocument();
  });
  it.each(["missing", "stale", "invalid", "clock_skew"] as const)(
    "%s never displays passed observations",
    (freshness) => {
      render(
        <Readiness
          workspace={{ ...base, setup_snapshot: { ...saved, freshness } }}
          t={translator("en")}
        />,
      );
      expect(screen.queryByText(/Reported pass/)).not.toBeInTheDocument();
      expect(
        screen.getByText(/Required environment presence: Unknown/),
      ).toBeInTheDocument();
    },
  );
  it("updates the same view when the selected workspace snapshot changes", () => {
    const view = render(
      <Readiness
        workspace={{ ...base, setup_snapshot: saved }}
        t={translator("en")}
      />,
    );
    view.rerender(<Readiness workspace={base} t={translator("en")} />);
    expect(screen.getByText(/No saved snapshot/)).toBeInTheDocument();
    expect(screen.queryByText("2026-10-22T12:00:00Z")).not.toBeInTheDocument();
    expect(screen.queryByText(/Reported pass/)).not.toBeInTheDocument();
  });
  it("has Traditional Chinese evidence boundaries", () => {
    render(
      <Readiness
        workspace={{ ...base, setup_snapshot: saved }}
        t={translator("zh-TW")}
      />,
    );
    expect(screen.getByText(/不是即時驗證/)).toBeInTheDocument();
    expect(
      screen.getByText(/必要環境變數是否存在: 曾回報通過（歷史）/),
    ).toBeInTheDocument();
    expect(screen.getByText(/不保證能力仍有效/)).toBeInTheDocument();
  });
});
