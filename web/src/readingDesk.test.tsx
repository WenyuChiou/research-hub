import { act, render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LiteratureLibrary } from "./LiteratureLibrary";
import { translator } from "./i18n";
import type { ResearchRecord } from "./types";

const t=translator("en");
const sources:ResearchRecord[]=[
 {id:"study",kind:"source",data:{title:"Synthetic study",category:"human",summary:"Preserved human wording.",reading_level:"abstract-snippet",identity_status:"unverified",locator:"https://example.invalid/study"}},
 {id:"model",kind:"source",data:{title:"Synthetic model",category:"llm",reading_level:"abstract",identity_status:"unverified",locator:"https://example.invalid/model"}},
];
function media(matches:boolean){
 const listeners=new Set<(event:{matches:boolean})=>void>();
 vi.stubGlobal("matchMedia",()=>({matches,media:"(max-width: 1080px)",addEventListener:(_:string,fn:(e:{matches:boolean})=>void)=>listeners.add(fn),removeEventListener:(_:string,fn:(e:{matches:boolean})=>void)=>listeners.delete(fn)}));
 return (next:boolean)=>listeners.forEach(fn=>fn({matches:next}));
}
const props=()=>({sources,screenings:[],t,onScreen:vi.fn(),onPrepare:vi.fn()});
afterEach(()=>vi.unstubAllGlobals());

describe("reading desk",()=>{
 it("uses real category controls and the same search/filter state",async()=>{
  media(false);const user=userEvent.setup();render(<LiteratureLibrary {...props()}/>);
  const categories=screen.getByRole("group",{name:"Categories"});
  await user.click(within(categories).getByRole("button",{name:new RegExp(t("catalogLlm"))}));
  expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(1);
  expect(screen.getByRole("heading",{name:"Synthetic model"})).toBeVisible();
  await user.type(screen.getByRole("searchbox"),"no-match");expect(screen.getByText(t("catalogNoMatches"))).toBeVisible();
  await user.click(screen.getByRole("button",{name:t("catalogClearFilters")}));
  expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(2);
 });
 it("keeps compact mode in one pane and restores filter, selected row and focus",async()=>{
  media(true);vi.stubGlobal("scrollTo",vi.fn());const user=userEvent.setup();const before=JSON.stringify(sources);
  render(<LiteratureLibrary {...props()}/>);
  const reader=screen.getByRole("complementary",{hidden:true});
  expect(reader).not.toBeVisible();
  await user.type(screen.getByRole("searchbox"),"study");
  const row=screen.getByRole("button",{name:"Synthetic study"});row.focus();await user.keyboard("{Enter}");
  expect(screen.getByRole("heading",{name:"Synthetic study"})).toHaveFocus();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  expect(screen.getByText("Preserved human wording.")).toBeVisible();
  await user.click(screen.getByRole("button",{name:t("catalogBackToList")}));
  await waitFor(()=>expect(row).toHaveFocus());
  expect(screen.getByRole("searchbox")).toHaveValue("study");expect(screen.getByRole("table")).toBeVisible();
  expect(JSON.stringify(sources)).toBe(before);
 });
 it("keeps keyboard recovery in the compact search after clearing an empty result",async()=>{
  media(true);const user=userEvent.setup();const p=props();const before=JSON.stringify(sources);
  render(<LiteratureLibrary {...p}/>);
  const search=screen.getByRole("searchbox",{name:t("catalogSearch")});
  await user.type(search,"no-match");
  expect(screen.getByText(t("catalogNoMatches"))).toBeVisible();
  await user.tab();expect(screen.getByRole("combobox",{name:t("catalogCategory")})).toHaveFocus();
  await user.tab();expect(screen.getByRole("button",{name:t("catalogClearFilters")})).toHaveFocus();
  await user.keyboard("{Enter}");
  expect(search).toHaveFocus();expect(search).toHaveValue("");
  expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(2);
  await user.keyboard("study");
  expect(search).toHaveValue("study");
  expect(within(screen.getByRole("table")).getByRole("button",{name:"Synthetic study"})).toBeVisible();
  expect(within(screen.getByRole("table")).queryByRole("button",{name:"Synthetic model"})).not.toBeInTheDocument();
  expect(JSON.stringify(sources)).toBe(before);expect(p.onScreen).not.toHaveBeenCalled();expect(p.onPrepare).not.toHaveBeenCalled();
 });
 it("returns to list if a refresh removes the selected compact paper",async()=>{
  media(true);vi.stubGlobal("scrollTo",vi.fn());const user=userEvent.setup();const p=props();
  const {rerender}=render(<LiteratureLibrary {...p}/>);
  await user.click(screen.getByRole("button",{name:"Synthetic study"}));
  rerender(<LiteratureLibrary {...p} sources={[sources[1]]}/>);
  expect(await screen.findByText("The selected item is unavailable in this view. Choose another item.")).toBeVisible();
  expect(screen.getByRole("table")).toBeVisible();expect(screen.getByRole("searchbox")).toHaveFocus();
  expect(screen.queryByText("Preserved human wording.")).not.toBeInTheDocument();
 });
 it("moves focused category controls across the shared breakpoint without clearing filters",async()=>{
  const resize=media(false);const user=userEvent.setup();render(<LiteratureLibrary {...props()}/>);
  const categories=screen.getByRole("group",{name:t("catalogCategories")});
  const llm=within(categories).getByRole("button",{name:new RegExp(t("catalogLlm"))});
  await user.click(llm);expect(llm).toHaveFocus();
  act(()=>resize(true));
  expect(screen.getByRole("combobox",{name:t("catalogCategory")})).toHaveFocus();
  expect(screen.getByRole("combobox",{name:t("catalogCategory")})).toHaveValue("llm");
  // CSS may blur the select before its media-query change callback arrives.
  screen.getByRole("combobox",{name:t("catalogCategory")}).blur();
  expect(document.body).toHaveFocus();
  act(()=>resize(false));expect(llm).toHaveFocus();
  expect(within(screen.getByRole("table")).getAllByRole("button")).toHaveLength(1);
 });
 it("removes sidebar portal controls when Literature is inactive",()=>{
  media(false);const host=document.createElement("div");document.body.appendChild(host);
  const p=props();const {rerender,unmount}=render(<LiteratureLibrary {...p} categoryHost={host} observationRead={{projectId:"synthetic",artifacts:[],active:true}}/>);
  expect(within(host).getByRole("group",{name:t("catalogCategories")})).toBeVisible();
  rerender(<LiteratureLibrary {...p} categoryHost={host} observationRead={{projectId:"synthetic",artifacts:[],active:false}}/>);
  expect(host).toBeEmptyDOMElement();unmount();host.remove();
 });
 it("Escape returns to the exact compact row without modifying the saved summary",async()=>{
  media(true);vi.stubGlobal("scrollTo",vi.fn());const user=userEvent.setup();render(<LiteratureLibrary {...props()}/>);
  const row=screen.getByRole("button",{name:"Synthetic study"});await user.click(row);
  await user.keyboard("{Escape}");expect(row).toHaveFocus();
  expect(screen.queryByRole("heading",{name:"Synthetic study"})).not.toBeInTheDocument();
  expect(sources[0].data.summary).toBe("Preserved human wording.");
 });
 it("keeps the focused desktop reader and exact paper visible when narrowing",()=>{
  const resize=media(false);render(<LiteratureLibrary {...props()}/>);
  const heading=screen.getByRole("heading",{name:"Synthetic study"});heading.focus();
  act(()=>resize(true));expect(heading).toBeVisible();expect(heading).toHaveFocus();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
 });
 it("does not restore stale category focus after moving to an external control",async()=>{
  const resize=media(true);const user=userEvent.setup();
  render(<><button>External navigation</button><LiteratureLibrary {...props()}/></>);
  screen.getByRole("combobox",{name:t("catalogCategory")}).focus();
  const outside=screen.getByRole("button",{name:"External navigation"});await user.click(outside);
  outside.blur();expect(document.body).toHaveFocus();
  act(()=>resize(false));expect(document.body).toHaveFocus();
 });
 it("keeps a desktop Back target in the compact list and category focus outside the reader",async()=>{
  const resize=media(false);const user=userEvent.setup();render(<LiteratureLibrary {...props()}/>);
  const row=screen.getByRole("button",{name:"Synthetic study"});await user.click(row);
  await user.click(screen.getByRole("button",{name:t("catalogBackToList")}));
  act(()=>resize(true));expect(row).toBeVisible();expect(row).toHaveFocus();
  act(()=>resize(false));await user.click(row);
  const categories=screen.getByRole("group",{name:t("catalogCategories")});
  await user.click(within(categories).getByRole("button",{name:new RegExp(t("catalogLlm"))}));
  act(()=>resize(true));expect(screen.getByRole("combobox",{name:t("catalogCategory")})).toHaveFocus();
  expect(screen.queryByRole("heading",{name:"Synthetic model"})).not.toBeInTheDocument();
 });
});
