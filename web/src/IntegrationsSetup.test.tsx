import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { IntegrationsSetup } from "./IntegrationsSetup";
import { translator } from "./i18n";
import type { Workspace } from "./types";
vi.mock("./api", () => ({
  api: vi.fn(() => new Promise(() => {})),
  segment: encodeURIComponent,
}));
afterEach(cleanup);
const t = translator("en");
const saved = {
  schema_version: 1,
  source: "saved_local_setup_snapshot",
  freshness: "saved",
  current_status: "unknown",
  observed_at: "2026-10-25T00:00:00Z",
  age_seconds: 1,
  display_max_age_seconds: 86400,
  components: { vault: "passed", zotero: "failed", notebooklm_auth: "unknown" },
};
const workspace = (snapshot: unknown) =>
  ({ setup_snapshot: snapshot }) as Workspace;
async function open() {
  await userEvent.click(
    screen.getByRole("button", { name: t("integrationsSetup") }),
  );
  return screen.getByRole("dialog");
}
it("offers a compact footer entry before project load; opening a separate panel causes no extra API calls", async () => {
  const { api } = await import("./api");
  render(<App />);
  const button = screen.getByRole("button", { name: t("integrationsSetup") });
  expect(button.closest(".sidebar-footer")).not.toBeNull();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  const before = vi.mocked(api).mock.calls.length;
  const panel = await open();
  expect(panel.closest("aside")).toBeNull();
  expect(within(panel).getByText("python -m research_hub setup")).toBeVisible();
  expect(vi.mocked(api).mock.calls.length).toBe(before);
});
it.each(["en", "zh-TW"] as const)(
  "supports keyboard open, Escape and close focus restoration in %s",
  async (locale) => {
    const tr = translator(locale);
    render(<IntegrationsSetup workspace={null} t={tr} />);
    const button = screen.getByRole("button", {
      name: tr("integrationsSetup"),
    });
    button.focus();
    await userEvent.keyboard("{Enter}");
    expect(
      screen.getByRole("heading", { name: tr("integrationsSetup") }),
    ).toHaveFocus();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(button).toHaveFocus();
    await userEvent.click(button);
    await userEvent.click(
      screen.getByRole("button", { name: tr("integrationClose") }),
    );
    expect(button).toHaveFocus();
  },
);
it.each(["hashchange", "popstate"])(
  "closes on %s without taking over newer focus",
  async (event) => {
    render(
      <>
        <button>New navigation target</button>
        <IntegrationsSetup workspace={null} t={t} />
      </>,
    );
    await open();
    const target = screen.getByRole("button", {
      name: "New navigation target",
    });
    target.focus();
    fireEvent(window, new Event(event));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(target).toHaveFocus();
  },
);
it("closes on project replacement but not an ordinary refresh", async () => {
  const { rerender } = render(
    <IntegrationsSetup workspace={workspace(saved)} projectId="one" t={t} />,
  );
  await open();
  rerender(
    <IntegrationsSetup
      workspace={workspace({ ...saved })}
      projectId="one"
      t={t}
    />,
  );
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  rerender(
    <IntegrationsSetup workspace={workspace(saved)} projectId="two" t={t} />,
  );
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
it("exposes exact official links but no secret inputs or raw snapshot values", async () => {
  render(
    <IntegrationsSetup
      workspace={workspace({
        ...saved,
        api_key: "SECRET_KEY",
        path: "PRIVATE_VAULT",
        error: "PRIVATE_ERROR",
        components: { ...saved.components, zotero: "SECRET_STATUS" },
      })}
      t={t}
    />,
  );
  const panel = await open();
  expect(panel.textContent).not.toMatch(/SECRET|PRIVATE/);
  expect(panel.textContent).toContain(t("snapshotPassed"));
  expect(panel.querySelector("input,textarea")).toBeNull();
  expect(Array.from(panel.querySelectorAll("a")).map((a) => a.href)).toEqual(
    expect.arrayContaining([
      "https://www.zotero.org/settings/keys",
      "https://help.obsidian.md/manage-vaults",
      "https://notebook.google.com/",
      "https://github.com/WenyuChiou/research-hub/blob/fix/nlm-085-integrations-guidance/docs/setup.md",
    ]),
  );
  for (const a of panel.querySelectorAll("a"))
    expect(a.rel).toBe("noopener noreferrer");
});
it.each(["missing", "stale", "invalid", "clock_skew"])(
  "does not promote %s observations",
  async (freshness) => {
    render(
      <IntegrationsSetup
        workspace={workspace({ ...saved, freshness })}
        t={t}
      />,
    );
    const panel = await open();
    expect(panel.textContent).not.toContain(t("snapshotPassed"));
    expect(panel.textContent).not.toContain(t("snapshotFailed"));
    expect(panel.textContent).toContain("unknown, not disconnected");
  },
);
it.each(["constructor", "toString", "__proto__"])(
  "maps inherited status %s to unknown",
  async (status) => {
    render(
      <IntegrationsSetup
        workspace={workspace({
          ...saved,
          components: {
            vault: status,
            zotero: status,
            notebooklm_auth: status,
          },
        })}
        t={t}
      />,
    );
    const panel = await open();
    expect(panel.textContent?.match(/Unknown/g)).toHaveLength(3);
  },
);
it("unsupported snapshot version remains unknown and never probes", async () => {
  const spy = vi.spyOn(globalThis, "fetch");
  render(
    <IntegrationsSetup
      workspace={workspace({ ...saved, schema_version: 99 })}
      t={t}
    />,
  );
  const panel = await open();
  expect(panel.textContent).not.toContain(t("snapshotPassed"));
  expect(spy).not.toHaveBeenCalled();
  spy.mockRestore();
});

it("guides first use without claiming an integration is disconnected or requiring accounts", async () => {
  const { api } = await import("./api");
  vi.mocked(api).mockResolvedValueOnce({
    ok: true,
    projects: [],
    capabilities: {
      codex: { status: "unavailable", message: "" },
      writing: { status: "unavailable", message: "" },
      approval: { status: "unavailable", message: "" },
    },
    protection_scope: "local",
  });
  render(<App />);
  expect(await screen.findByText(t("integrationFirstUse"))).toBeVisible();
  expect(
    screen.getByRole("button", { name: t("integrationsSetup") }),
  ).toBeEnabled();
});

it("uses an explicit readable theme for the footer trigger instead of inherited sidebar text on native gray", () => {
  render(<IntegrationsSetup workspace={null} t={t}/>);
  expect(screen.getByRole("button",{name:t("integrationsSetup")})).toHaveClass("button", "secondary");
});
