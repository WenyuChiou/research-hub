import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { LibraryCollection, type LibrarySnapshot } from "./LibraryCollection";
import { identityMatches } from "./libraryIdentity";
import { translator } from "./i18n";
import type { ResearchRecord } from "./types";

const t = translator("en");
const workspace: ResearchRecord = {id:"workspace-one",kind:"source",data:{title:"Workspace item",doi:"10.1000/example",reading_scope:"abstract"}};
const note: ResearchRecord = {id:"obsidian:1234567890abcdef12345678",kind:"library-note",data:{title:"Saved Obsidian note",origin:"obsidian",read_only:true,doi:"10.1000/EXAMPLE",category:"Synthetic collection",note_path:"raw/selected/note.md",reading_level:"note-metadata",metadata_status:"available"}};
const snapshot: LibrarySnapshot = {schema_version:1,captured_at:"2026-10-31T17:00:00Z",vault_label:"Synthetic vault",read_only:true,body_read:false,collections:[{id:"selected",name:"Synthetic collection",note_count:1}],notes:[note]};
const props = () => ({sources:[workspace],screenings:[],t,onScreen:vi.fn(),onPrepare:vi.fn()});
afterEach(() => vi.unstubAllGlobals());

it("loads only on request, keeps original collections and hides writes for vault notes", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(snapshot)));
  vi.stubGlobal("fetch",fetch);
  const user = userEvent.setup();
  const callbacks = props();
  render(<LibraryCollection {...callbacks} />);
  expect(fetch).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button",{name:t("libraryLoad")}));
  expect(fetch.mock.calls[0][0]).toBe("/api/v1/library/snapshot");
  expect(await screen.findByRole("heading",{name:"Saved Obsidian note"})).toBeVisible();
  expect(screen.getByText(t("libraryReadOnly"))).toBeVisible();
  expect(screen.getByText("raw/selected/note.md")).toBeVisible();
  expect(screen.queryByText(t("catalogScreening"))).toBeNull();
  expect(screen.queryByRole("button",{name:t("catalogSourceTools")})).toBeNull();
  expect(screen.getAllByText(t("libraryIdentityMatch")).length).toBeGreaterThan(0);
  await user.selectOptions(screen.getByLabelText(t("libraryScope")),"all");
  expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(2);
  await user.selectOptions(screen.getByLabelText(t("libraryScope")),"workspace");
  expect(screen.getByText(t("catalogScreening"))).toBeVisible();
  expect(callbacks.onScreen).not.toHaveBeenCalled();
  expect(callbacks.onPrepare).not.toHaveBeenCalled();
});

it("a disconnected reload retains dated metadata and does not misreport live sync", async () => {
  vi.stubGlobal("fetch",vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(snapshot))).mockRejectedValueOnce(new TypeError("offline")));
  const user = userEvent.setup();
  render(<LibraryCollection {...props()} />);
  await user.click(screen.getByRole("button",{name:t("libraryLoad")}));
  await screen.findByRole("heading",{name:"Saved Obsidian note"});
  await user.click(screen.getByRole("button",{name:t("libraryReload")}));
  expect(await screen.findByRole("alert")).toHaveTextContent(t("libraryRetained"));
  expect(screen.getByRole("heading",{name:"Saved Obsidian note"})).toBeVisible();
  await user.click(screen.getByText(t("librarySnapshotDetails"),{exact:true}));
  expect(screen.getByText(new RegExp(snapshot.captured_at))).toBeVisible();
});

it("rejects untrusted snapshot rows and preserves the project list", async () => {
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response(JSON.stringify({...snapshot,notes:[workspace]}))));
  const user = userEvent.setup();
  render(<LibraryCollection {...props()} />);
  await user.click(screen.getByRole("button",{name:t("libraryLoad")}));
  expect(await screen.findByRole("alert")).toHaveTextContent(t("libraryUnavailable"));
  expect(screen.getByRole("heading",{name:"Workspace item"})).toBeVisible();
});

it("matches only saved identity, never title or absent identifiers, and keeps both records", () => {
  const sameTitle = {...workspace,id:"different",data:{title:"Workspace item"}};
  const unsafe = {...workspace,id:"unsafe",data:{locator:"javascript:alert(1)"}};
  const map = identityMatches([workspace,note,sameTitle,unsafe]);
  expect(map.get(workspace.id)?.map(item=>item.id)).toEqual([note.id]);
  expect(map.get(sameTitle.id)).toEqual([]);
  expect(map.get(unsafe.id)).toEqual([]);
});
