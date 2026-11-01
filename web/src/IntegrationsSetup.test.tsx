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
  expect(panel.querySelector('input[type="password"],textarea')).toBeNull();
  expect(within(panel).getByRole("textbox", {name:t("obsidianVaultPath")})).toBeDisabled();
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

it("separates all current connection states from saved observations and explains the owner login boundary", async () => {
  render(<IntegrationsSetup workspace={workspace(saved)} t={t} />);
  const panel = await open();
  expect(within(panel).getAllByText(t("integrationNotChecked"))).toHaveLength(3);
  expect(within(panel).getAllByText(t("integrationSavedObservation"))).toHaveLength(3);
  expect(within(panel).getByText(t("snapshotPassed"))).toBeVisible();
  expect(within(panel).getByText(t("snapshotFailed"))).toBeVisible();
  expect(within(panel).getByText(t("integrationNlmPrerequisites"))).toBeVisible();
  expect(within(panel).getByText("python -m research_hub notebooklm login --auto-detect")).toBeVisible();
  expect(within(panel).getByRole("form", { name: t("zoteroDraft") })).toBeVisible();
  expect(within(panel).queryByRole("button", { name: /save|connect|login/i })).not.toBeInTheDocument();
});

it("discards the Zotero draft when closing or changing project without fetching or saving", async () => {
  const { api } = await import("./api");
  const { rerender } = render(<IntegrationsSetup workspace={null} projectId="one" t={t} />);
  const before = vi.mocked(api).mock.calls.length;
  await open();
  await userEvent.type(screen.getByRole("textbox", { name: t("zoteroLibraryId") }), "123456");
  await userEvent.selectOptions(screen.getByRole("combobox"), "user");
  await userEvent.click(screen.getByRole("button", { name: t("zoteroCheckFormat") }));
  expect(screen.getByText(t("zoteroFormatValid"))).toBeVisible();
  await userEvent.keyboard("{Escape}");
  await open();
  expect(screen.getByRole("textbox", { name: t("zoteroLibraryId") })).toHaveValue("");
  expect(screen.getByRole("combobox")).toHaveValue("");
  await userEvent.type(screen.getByRole("textbox", { name: t("zoteroLibraryId") }), "654321");
  rerender(<IntegrationsSetup workspace={null} projectId="two" t={t} />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  await open();
  expect(screen.getByRole("textbox", { name: t("zoteroLibraryId") })).toHaveValue("");
  expect(vi.mocked(api).mock.calls.length).toBe(before);
});

it.each(["en", "zh-TW"] as const)("shows observation provenance, exact UTC time and historical age separately from destination and current connection in %s", async (locale) => {
  const tr = translator(locale);
  const { api } = await import("./api");
  const calls = vi.mocked(api).mock.calls.length;
  render(<IntegrationsSetup workspace={workspace({...saved,observed_at:"2026-10-25T00:00:00.123456Z"})} t={tr} />);
  await userEvent.click(screen.getByRole("button", {name:tr("integrationsSetup")}));
  const panel = within(screen.getByRole("dialog"));
  expect(panel.getByText(tr("integrationSavedSetupSource"))).toBeVisible();
  expect(panel.getByText("2026-10-25T00:00:00.123456Z")).toHaveAttribute("datetime", "2026-10-25T00:00:00.123456Z");
  expect(panel.getByText(tr("integrationFreshSaved"))).toBeVisible();
  expect(panel.getAllByText(tr("integrationNotChecked"))).toHaveLength(3);
  expect(panel.getAllByText(tr("integrationDestinationUnknown"))).toHaveLength(2);
  expect(panel.getByText(tr("integrationNoStartupVault"))).toBeVisible();
  expect(vi.mocked(api).mock.calls.length).toBe(calls);
});

it.each([
  ["missing", "integrationFreshMissing"], ["stale", "integrationFreshStale"],
  ["invalid", "integrationFreshInvalid"], ["clock_skew", "integrationFreshClockSkew"],
] as const)("labels %s observations without turning a saved pass into current connectivity", async (freshness, label) => {
  render(<IntegrationsSetup workspace={workspace({...saved,freshness})} t={t} />);
  const panel = await open();
  expect(within(panel).getByText(t(label))).toBeVisible();
  expect(within(panel).getAllByText(t("integrationNotChecked"))).toHaveLength(3);
  expect(panel.textContent).not.toContain(t("snapshotPassed"));
  expect(panel.textContent).not.toContain(t("snapshotFailed"));
});

it.each(["SECRET_TIME", "2026-10-25T00:00:00Z?token=SECRET", "2026-02-30T00:00:00Z", "2026-10-25T00:00:00"])(
  "does not expose or trust malformed observation time %s", async (observed_at) => {
    render(<IntegrationsSetup workspace={workspace({...saved,observed_at,source_path:"PRIVATE_PATH",token:"SECRET_TOKEN"})} t={t} />);
    const panel = await open();
    expect(panel.querySelector("time")).toBeNull();
    expect(within(panel).getByText(t("integrationFreshInvalid"))).toBeVisible();
    expect(panel.innerHTML).not.toMatch(/SECRET|PRIVATE/);
    expect(panel.textContent).not.toContain(t("snapshotPassed"));
  },
);

it("shows an exact startup-selected Obsidian destination without a probe or connection claim; Zotero draft checking remains unsaved", async () => {
  const { api } = await import("./api");
  const calls = vi.mocked(api).mock.calls.length;
  const scoped: Workspace = {ok:true,projects:[],protection_scope:"synthetic",setup_snapshot:{...saved,current_status:"unknown",freshness:"stale"},capabilities:{codex:{status:"unavailable",message:"synthetic"},writing:{status:"unavailable",message:"synthetic"},approval:{status:"unavailable",message:"synthetic"},obsidian_validation:{version:1,status:"available",read_only:true,scope:"startup_selected_exact_vault",authorized_vault:"/synthetic/selected-vault"}}};
  render(<IntegrationsSetup workspace={scoped} t={t} />);
  const panel = await open();
  expect(within(panel).getByText(t("integrationSelectedVault"))).toBeVisible();
  expect(within(panel).getByRole("textbox", {name:t("obsidianVaultPath")})).toHaveValue("/synthetic/selected-vault");
  await userEvent.type(within(panel).getByRole("textbox", {name:t("zoteroLibraryId")}), "123456");
  await userEvent.selectOptions(within(panel).getByRole("combobox", {name:t("zoteroLibraryType")}), "group");
  await userEvent.click(within(panel).getByRole("button", {name:t("zoteroCheckFormat")}));
  expect(within(panel).getAllByText(t("integrationDestinationUnknown"))).toHaveLength(2);
  expect(within(panel).getAllByText(t("integrationNotChecked"))).toHaveLength(3);
  expect(within(panel).getByText(t("zoteroFormatValid"))).toBeVisible();
  expect(vi.mocked(api).mock.calls.length).toBe(calls);
});

it.each([
  {label:"null",value:null}, {label:"noncoercible object",value:{toString:null}},
  {label:"array",value:["SECRET_FRESHNESS"]}, {label:"prototype name",value:"__proto__"},
])("handles malformed freshness $label without a closed-panel render failure or raw-value leak", async ({value}) => {
  render(<IntegrationsSetup workspace={workspace({...saved,freshness:value})} t={t} />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  const panel = await open();
  expect(within(panel).getByText(t("integrationFreshInvalid"))).toBeVisible();
  expect(panel.textContent).not.toContain(t("snapshotPassed"));
  expect(panel.innerHTML).not.toContain("SECRET_FRESHNESS");
});
