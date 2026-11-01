import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { api, ApiError } from "./api";
import { ObsidianValidationForm } from "./ObsidianValidationForm";
import { IntegrationsSetup } from "./IntegrationsSetup";
import { translator } from "./i18n";
import type { Workspace } from "./types";

vi.mock("./api", () => ({api:vi.fn(),ApiError:class ApiError extends Error {constructor(message:string,public code:string,public status:number){super(message);}},segment:encodeURIComponent}));
const t = translator("en");
const scope = {version:1,status:"available",read_only:true,scope:"startup_selected_exact_vault",authorized_vault:"/synthetic/selected-vault"};
const response = (status="valid") => ({ok:true,status,read_only:true,saved:false,note_bodies_read:false,observed_at:"2026-10-31T00:00:00Z",collection_count:2});
afterEach(()=>{vi.clearAllMocks();vi.useRealTimers();});

it("does not probe without a startup scope or merely by rendering the form", () => {
  render(<ObsidianValidationForm t={t} />);
  expect(screen.getByRole("textbox",{name:t("obsidianVaultPath")})).toBeDisabled();
  expect(screen.getByRole("button",{name:t("obsidianValidate")})).toBeDisabled();
  expect(screen.getByText(t("obsidianUnavailable"))).toBeVisible();
  expect(api).not.toHaveBeenCalled();
});
it("submits the explicit path once and reports metadata scope without saving", async () => {
  vi.mocked(api).mockResolvedValue(response());
  const user=userEvent.setup();
  render(<ObsidianValidationForm capability={scope} t={t} />);
  expect(screen.getByText(t("obsidianUnknown"))).toBeVisible();
  expect(api).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button",{name:t("obsidianValidate")}));
  expect(await screen.findByText(t("obsidianValid"))).toBeVisible();
  expect(api).toHaveBeenCalledWith("/integrations/obsidian/validate",{vault_path:scope.authorized_vault},expect.any(AbortSignal));
  expect(screen.getByText(t("obsidianResultScope"),{exact:false})).toBeVisible();
  expect(screen.queryByRole("button",{name:/save/i})).toBeNull();
});
it.each([
  ["not_found","obsidianNotFound"],["not_directory","obsidianNotDirectory"],["not_vault","obsidianNotVault"],
  ["registry_missing","obsidianRegistryMissing"],["invalid_registry","obsidianRegistryInvalid"],
  ["registry_mismatch","obsidianRegistryMismatch"],["unsafe_path","obsidianUnsafePath"],
] as const)("shows the bounded %s result without declaring connected", async (status,key)=>{
  vi.mocked(api).mockResolvedValue(response(status));
  const user=userEvent.setup();render(<ObsidianValidationForm capability={scope} t={t} />);
  await user.click(screen.getByRole("button",{name:t("obsidianValidate")}));
  expect(await screen.findByText(t(key))).toBeVisible();
  expect(screen.queryByText(t("obsidianValid"))).toBeNull();
});
it("keeps a denied path error separate from a network error and never displays raw exceptions", async()=>{
  vi.mocked(api).mockRejectedValueOnce(new ApiError("PRIVATE_SERVER_TEXT","vault_scope_denied",403)).mockRejectedValueOnce(new Error("PRIVATE_SERVER_TEXT"));
  const user=userEvent.setup();render(<ObsidianValidationForm capability={scope} t={t} />);
  const input=screen.getByRole("textbox",{name:t("obsidianVaultPath")});
  await user.clear(input);await user.type(input,"/synthetic/other-vault");
  await user.click(screen.getByRole("button",{name:t("obsidianValidate")}));
  expect(await screen.findByRole("alert")).toHaveTextContent(t("obsidianScopeDenied"));
  await user.click(screen.getByRole("button",{name:t("obsidianValidate")}));
  expect(await screen.findByRole("alert")).toHaveTextContent(t("obsidianError"));
  expect(document.body.textContent).not.toContain("PRIVATE_SERVER_TEXT");
});
it("cancels waiting and ignores the late result without replaying the request", async()=>{
  let resolve!:(value:unknown)=>void;
  vi.mocked(api).mockImplementation(()=>new Promise(done=>{resolve=done;}) as ReturnType<typeof api>);
  const user=userEvent.setup();render(<ObsidianValidationForm capability={scope} t={t} />);
  await user.click(screen.getByRole("button",{name:t("obsidianValidate")}));
  expect(screen.getByText(t("obsidianLoading"))).toBeVisible();
  const signal=vi.mocked(api).mock.calls[0][2] as AbortSignal;
  await user.click(screen.getByRole("button",{name:t("cancel")}));
  expect(signal.aborted).toBe(true);
  await act(async()=>resolve(response()));
  expect(screen.getByText(t("obsidianCancelled"))).toBeVisible();
  expect(screen.queryByText(t("obsidianValid"))).toBeNull();
  expect(api).toHaveBeenCalledTimes(1);
});
it("times out a nonresponsive local request instead of leaving loading forever",async()=>{
  vi.useFakeTimers();
  vi.mocked(api).mockImplementation(()=>new Promise(()=>{}) as ReturnType<typeof api>);
  render(<ObsidianValidationForm capability={scope} t={t} />);
  fireEvent.submit(screen.getByRole("form",{name:t("obsidianValidation")}));
  await act(async()=>{vi.advanceTimersByTime(10001);});
  expect(screen.getByRole("alert")).toHaveTextContent(t("obsidianTimeout"));
  expect(screen.getByRole("button",{name:t("obsidianValidate")})).toBeEnabled();
});
it("closing and returning clears unsaved input and aborts pending validation",async()=>{
  let resolve!:(value:unknown)=>void;
  vi.mocked(api).mockImplementation(()=>new Promise(done=>{resolve=done;}) as ReturnType<typeof api>);
  const user=userEvent.setup();
  render(<IntegrationsSetup workspace={{capabilities:{obsidian_validation:scope}} as Workspace} t={t} />);
  await user.click(screen.getByRole("button",{name:t("integrationsSetup")}));
  const dialog=screen.getByRole("dialog");
  await user.click(within(dialog).getByRole("button",{name:t("obsidianValidate")}));
  const signal=vi.mocked(api).mock.calls[0][2] as AbortSignal;
  await user.click(within(dialog).getByRole("button",{name:t("integrationClose")}));
  expect(signal.aborted).toBe(true);
  await act(async()=>resolve(response()));
  await user.click(screen.getByRole("button",{name:t("integrationsSetup")}));
  expect(screen.getByText(t("obsidianUnknown"))).toBeVisible();
  expect(screen.getByRole("textbox",{name:t("obsidianVaultPath")})).toHaveValue(scope.authorized_vault);
  expect(api).toHaveBeenCalledTimes(1);
});
