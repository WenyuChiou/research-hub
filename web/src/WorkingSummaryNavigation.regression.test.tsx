import App from "./App";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { WorkingSummaryEditor } from "./WorkingSummaryEditor";
import { LiteratureLibrary } from "./LiteratureLibrary";
import { observationArtifacts, registeredObservationArtifacts } from "./ObservationPreview";
import { translator } from "./i18n";
import type { ResearchRecord } from "./types";

const sha = "a".repeat(64), revision = "1".repeat(64), freshRevision = "2".repeat(64);
const t = translator("en"), draft = "  Synthetic unsaved human text\n  ";
afterEach(()=>vi.unstubAllGlobals());
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), {status, headers:{"Content-Type":"application/json"}});
function deferred() {
  let resolve!: (value: Response) => void;
  const promise = new Promise<Response>(done => {resolve = done;});
  return {promise, resolve};
}
function fixture() {
  const record: ResearchRecord = {id:"source-one",kind:"source",data:{id:"one",title:"Synthetic source",source_records:[{observation_id:"obs-one",source_id:"one",work_id:"work-one",status:"available",evidence_level:"generated-summary",text_path:"report.md",text_sha256:sha}]}};
  const artifact = {id:"report-one",project_id:"project-one",source_record_id:record.id,path:"report.md",role:"evidence",sha256:sha,current:true};
  const context = {source_record_id:record.id,artifact_id:artifact.id,artifact_sha256:sha,revision,draft_text:"Synthetic generated prose",working_summary:null};
  const saved = {text:draft.trim(),artifact_id:artifact.id,artifact_sha256:sha,source_revision:freshRevision,previous_revision:revision,saved_at:"2026-11-05T00:00:00Z"};
  return {record,artifact,context,saved,scope:{projectId:"project-one",artifacts:[artifact],active:true},onSaved:vi.fn().mockResolvedValue(undefined)};
}
type Fixture = ReturnType<typeof fixture>;
const props = (f: Fixture) => ({record:f.record,scope:f.scope,t,onSaved:f.onSaved});
const review = () => screen.getByRole("button",{name:`${t("workingSummaryReview")} report-one`});
const savedResponse = (f: Fixture) => response({ok:true,record:{...f.record,data:{...f.record.data,working_summary:f.saved}},reused:false});
const readbackResponse = (f: Fixture) => response({ok:true,context:{...f.context,revision:freshRevision,working_summary:f.saved}});

it("does not start an editor or request while initially inactive", () => {
  const f=fixture(), fetch=vi.spyOn(globalThis,"fetch");
  const {rerender,container}=render(<WorkingSummaryEditor {...props(f)} scope={{...f.scope,active:false}} suspended/>);
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
  container.querySelectorAll("button").forEach(button=>fireEvent.click(button));
  expect(fetch).not.toHaveBeenCalled();
  rerender(<WorkingSummaryEditor {...props(f)}/>);
  expect(review()).toBeEnabled();expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});

it.each(["loading","ready","blocked","saving","checking"] as const)("retains the same %s session across inactive/active without new requests or focus",async phase=>{
  const f=fixture(), pending=deferred(), user=userEvent.setup();
  const fetch=vi.spyOn(globalThis,"fetch").mockImplementationOnce(()=>phase==="loading"?pending.promise:Promise.resolve(response({ok:true,context:f.context})));
  if(phase==="saving") fetch.mockImplementationOnce(()=>pending.promise);
  if(phase==="blocked"||phase==="checking") fetch.mockRejectedValueOnce(new TypeError("Synthetic response loss"));
  if(phase==="checking") fetch.mockImplementationOnce(()=>pending.promise);
  const {rerender}=render(<><button>Other page</button><WorkingSummaryEditor {...props(f)}/></>);
  await user.click(review());
  const dialog=screen.getByRole("dialog");
  let input:HTMLElement|undefined;
  if(phase!=="loading") {
    input=await screen.findByRole("textbox",{name:t("workingSummaryText")});fireEvent.change(input,{target:{value:draft}});
    if(phase!=="ready") await user.click(screen.getByRole("button",{name:t("workingSummarySave")}));
    if(phase==="blocked"||phase==="checking") await screen.findByText(t("workingSummaryUnknown"));
    if(phase==="checking") await user.click(screen.getByRole("button",{name:t("workingSummaryCheck")}));
  }
  const calls=fetch.mock.calls.length;
  rerender(<><button>Other page</button><WorkingSummaryEditor {...props(f)} scope={{...f.scope,active:false}} suspended/></>);
  const outside=screen.getByRole("button",{name:"Other page"});outside.focus();
  expect(dialog).not.toBeVisible();expect(dialog).toBeInTheDocument();
  // Even a synthetic activation of hidden controls cannot write, read or cancel.
  within(dialog).getAllByRole("button",{hidden:true}).forEach(button=>fireEvent.click(button));
  fireEvent.keyDown(dialog,{key:"Escape"});
  expect(fetch).toHaveBeenCalledTimes(calls);expect(outside).toHaveFocus();
  rerender(<><button>Other page</button><WorkingSummaryEditor {...props(f)}/></>);
  expect(screen.getByRole("dialog")).toBe(dialog);expect(outside).toHaveFocus();
  if(input){expect(screen.getByRole("textbox",{name:t("workingSummaryText")})).toBe(input);expect(input).toHaveValue(draft);}
  expect(fetch).toHaveBeenCalledTimes(calls);expect(f.onSaved).not.toHaveBeenCalled();
  if(phase==="loading") await act(async()=>pending.resolve(response({ok:true,context:f.context})));
  if(phase==="saving") await act(async()=>pending.resolve(savedResponse(f)));
  if(phase==="checking") await act(async()=>pending.resolve(readbackResponse(f)));
  if(phase==="blocked") expect(screen.getByRole("button",{name:t("workingSummarySave")})).toBeDisabled();
});

it.each(["loading","saving","checking","unknown","newer-edit"] as const)("accepts only in-session %s completion while hidden without reads, refresh or focus",async stage=>{
  const f=fixture(), pending=deferred(), user=userEvent.setup();
  const fetch=vi.spyOn(globalThis,"fetch").mockImplementationOnce(()=>stage==="loading"?pending.promise:Promise.resolve(response({ok:true,context:f.context})));
  if(stage==="saving"||stage==="unknown") fetch.mockImplementationOnce(()=>pending.promise);
  if(stage==="checking"||stage==="newer-edit") fetch.mockRejectedValueOnce(new TypeError("Synthetic response loss")).mockImplementationOnce(()=>pending.promise);
  const {rerender}=render(<><button>Other page</button><WorkingSummaryEditor {...props(f)}/></>);
  await user.click(review());
  let input:HTMLElement|undefined;
  if(stage!=="loading") {
    input=await screen.findByRole("textbox",{name:t("workingSummaryText")});fireEvent.change(input,{target:{value:draft}});
    await user.click(screen.getByRole("button",{name:t("workingSummarySave")}));
    if(stage==="checking"||stage==="newer-edit") {
      await screen.findByText(t("workingSummaryUnknown"));await user.click(screen.getByRole("button",{name:t("workingSummaryCheck")}));
      if(stage==="newer-edit") fireEvent.change(input,{target:{value:draft+"newer"}});
    }
  }
  const calls=fetch.mock.calls.length;
  rerender(<><button>Other page</button><WorkingSummaryEditor {...props(f)} scope={{...f.scope,active:false}} suspended/></>);
  const outside=screen.getByRole("button",{name:"Other page"});outside.focus();
  await act(async()=>pending.resolve(stage==="loading"?response({ok:true,context:f.context}):stage==="saving"?savedResponse(f):stage==="unknown"?response({ok:false,code:"response_lost"},503):readbackResponse(f)));
  expect(outside).toHaveFocus();expect(fetch).toHaveBeenCalledTimes(calls);expect(f.onSaved).not.toHaveBeenCalled();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  rerender(<><button>Other page</button><WorkingSummaryEditor {...props(f)}/></>);
  const restored=screen.getByRole("textbox",{name:t("workingSummaryText")});
  expect(restored).toHaveValue(stage==="loading"?f.context.draft_text:stage==="newer-edit"?draft+"newer":draft);
  expect(outside).toHaveFocus();expect(fetch).toHaveBeenCalledTimes(calls);
  if(stage==="saving"||stage==="checking") {
    await waitFor(()=>expect(f.onSaved).toHaveBeenCalledOnce());
    rerender(<><button>Other page</button><WorkingSummaryEditor {...props(f)} scope={{...f.scope,active:false}} suspended/></>);
    rerender(<><button>Other page</button><WorkingSummaryEditor {...props(f)}/></>);
    expect(f.onSaved).toHaveBeenCalledOnce();expect(restored).toBeDisabled();
  } else expect(f.onSaved).not.toHaveBeenCalled();
  if(stage==="unknown") expect(screen.getByRole("button",{name:t("workingSummarySave")})).toBeDisabled();
  if(stage==="newer-edit") expect(screen.getByText(t("workingSummaryEarlierSaved"))).toBeVisible();
});

it.each(["project","source","hash","unregistered"] as const)("invalidates a hidden pending save on %s change and never restores or refreshes it",async change=>{
  const f=fixture(), pending=deferred(), user=userEvent.setup();
  const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context})).mockImplementationOnce(()=>pending.promise);
  const {rerender}=render(<WorkingSummaryEditor {...props(f)}/>);
  await user.click(review());fireEvent.change(await screen.findByRole("textbox",{name:t("workingSummaryText")}),{target:{value:draft}});
  await user.click(screen.getByRole("button",{name:t("workingSummarySave")}));
  rerender(<WorkingSummaryEditor {...props(f)} scope={{...f.scope,active:false}} suspended/>);
  const artifact={...f.artifact}, record={...f.record,data:{...f.record.data}};
  const scope={...f.scope,artifacts:[artifact],active:false};
  if(change==="project"){scope.projectId="project-other";artifact.project_id=scope.projectId;}
  if(change==="source"){record.id="source-other";artifact.source_record_id=record.id;}
  if(change==="hash"){artifact.sha256="b".repeat(64);record.data.source_records=(record.data.source_records as Record<string,unknown>[]).map(row=>({...row,text_sha256:artifact.sha256}));}
  if(change==="unregistered") scope.artifacts=[];
  rerender(<WorkingSummaryEditor {...props(f)} record={record} scope={scope} suspended/>);
  await act(async()=>pending.resolve(savedResponse(f)));
  rerender(<WorkingSummaryEditor {...props(f)}/>);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();expect(screen.queryByDisplayValue(draft)).not.toBeInTheDocument();
  expect(f.onSaved).not.toHaveBeenCalled();expect(fetch.mock.calls.map(call=>call[1]?.method)).toEqual(["GET","POST"]);
});

it.each(["project","source","hash","unregistered"] as const)("discards an already-confirmed hidden save's deferred refresh on %s change",async change=>{
  const f=fixture(),pending=deferred(),user=userEvent.setup();
  const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context})).mockImplementationOnce(()=>pending.promise);
  const {rerender}=render(<WorkingSummaryEditor {...props(f)}/>);
  await user.click(review());fireEvent.change(await screen.findByRole("textbox",{name:t("workingSummaryText")}),{target:{value:draft}});
  await user.click(screen.getByRole("button",{name:t("workingSummarySave")}));
  rerender(<WorkingSummaryEditor {...props(f)} scope={{...f.scope,active:false}} suspended/>);
  await act(async()=>pending.resolve(savedResponse(f)));
  expect(f.onSaved).not.toHaveBeenCalled();expect(screen.getByText(t("workingSummarySaved"))).not.toBeVisible();
  const artifact={...f.artifact},record={...f.record,data:{...f.record.data}},scope={...f.scope,active:false,artifacts:[] as typeof f.scope.artifacts};
  scope.artifacts=[artifact];
  if(change==="project"){scope.projectId="project-other";artifact.project_id=scope.projectId;}
  if(change==="source"){record.id="source-other";artifact.source_record_id=record.id;}
  if(change==="hash"){artifact.sha256="b".repeat(64);record.data.source_records=(record.data.source_records as Record<string,unknown>[]).map(row=>({...row,text_sha256:artifact.sha256}));}
  if(change==="unregistered")scope.artifacts=[];
  rerender(<WorkingSummaryEditor {...props(f)} record={record} scope={scope} suspended/>);
  rerender(<WorkingSummaryEditor {...props(f)}/>);
  expect(review()).toBeEnabled();expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(f.onSaved).not.toHaveBeenCalled();expect(fetch).toHaveBeenCalledTimes(2);
});

it.each(["loading","checking"] as const)("fences late %s read after a suspended identity changes and another session opens",async stage=>{
  const f=fixture(),pending=deferred(),user=userEvent.setup();
  const fetch=vi.spyOn(globalThis,"fetch").mockImplementationOnce(()=>stage==="loading"?pending.promise:Promise.resolve(response({ok:true,context:f.context})));
  if(stage==="checking")fetch.mockRejectedValueOnce(new TypeError("Synthetic response loss")).mockImplementationOnce(()=>pending.promise);
  fetch.mockResolvedValueOnce(response({ok:true,context:{...f.context,draft_text:"New independent session"}}));
  const {rerender}=render(<WorkingSummaryEditor {...props(f)}/>);
  await user.click(review());
  if(stage==="checking"){
    fireEvent.change(await screen.findByRole("textbox",{name:t("workingSummaryText")}),{target:{value:draft}});
    await user.click(screen.getByRole("button",{name:t("workingSummarySave")}));await screen.findByText(t("workingSummaryUnknown"));
    await user.click(screen.getByRole("button",{name:t("workingSummaryCheck")}));
  }
  rerender(<WorkingSummaryEditor {...props(f)} scope={{...f.scope,active:false}} suspended/>);
  rerender(<WorkingSummaryEditor {...props(f)} scope={{...f.scope,active:false,artifacts:[]}} suspended/>);
  rerender(<WorkingSummaryEditor {...props(f)}/>);await user.click(review());
  const input=await screen.findByRole("textbox",{name:t("workingSummaryText")});expect(input).toHaveValue("New independent session");
  await act(async()=>pending.resolve(stage==="loading"?response({ok:true,context:f.context}):readbackResponse(f)));
  expect(input).toHaveValue("New independent session");expect(f.onSaved).not.toHaveBeenCalled();
  expect(fetch).toHaveBeenCalledTimes(stage==="loading"?2:4);
});

it("keeps ordinary inactive invalidation and the public observation active guard",async()=>{
  const f=fixture(),user=userEvent.setup();
  const fetch=vi.spyOn(globalThis,"fetch").mockImplementation(async()=>response({ok:true,context:f.context}));
  const inactive={...f.scope,active:false};
  expect(observationArtifacts(f.record,inactive)).toEqual([]);
  expect(registeredObservationArtifacts(f.record,inactive)).toEqual([f.artifact]);
  expect(fetch).not.toHaveBeenCalled();
  const {rerender}=render(<WorkingSummaryEditor {...props(f)}/>);await user.click(review());
  fireEvent.change(await screen.findByRole("textbox",{name:t("workingSummaryText")}),{target:{value:draft}});
  rerender(<WorkingSummaryEditor {...props(f)} scope={inactive}/>);
  expect(screen.queryByRole("dialog",{hidden:true})).not.toBeInTheDocument();
  rerender(<WorkingSummaryEditor {...props(f)}/>);expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  await user.click(review());expect(await screen.findByRole("textbox",{name:t("workingSummaryText")})).toHaveValue(f.context.draft_text);
  expect(fetch).toHaveBeenCalledTimes(2);
});

it("suspends a compact open reader for page navigation but still discards it on Back to list",async()=>{
  vi.stubGlobal("matchMedia",()=>({matches:true,media:"(max-width: 1080px)",addEventListener:vi.fn(),removeEventListener:vi.fn()}));
  vi.stubGlobal("scrollTo",vi.fn());
  const f=fixture(),user=userEvent.setup();let contextReads=0;
  vi.spyOn(globalThis,"fetch").mockImplementation(async url=>{
    if(String(url).includes("/working-summary?")){contextReads++;return response({ok:true,context:f.context});}
    return response({ok:false,code:"source_unavailable"},503);
  });
  const library=(active:boolean)=><div hidden={!active}><LiteratureLibrary sources={[f.record]} screenings={[]} t={t}
    onPrepare={vi.fn()} onScreen={vi.fn()} observationRead={{...f.scope,active}} pageSuspended={!active} onWorkingSummarySaved={f.onSaved}/></div>;
  const {rerender}=render(library(true));
  await user.click(screen.getByRole("button",{name:"Synthetic source"}));await user.click(review());
  const input=await screen.findByRole("textbox",{name:t("workingSummaryText")});fireEvent.change(input,{target:{value:draft}});
  rerender(library(false));expect(input).not.toBeVisible();rerender(library(true));
  expect(screen.getByRole("textbox",{name:t("workingSummaryText")})).toBe(input);expect(input).toHaveValue(draft);expect(contextReads).toBe(1);
  await user.click(screen.getByRole("button",{name:t("catalogBackToList")}));
  expect(screen.queryByRole("dialog",{hidden:true})).not.toBeInTheDocument();
  await user.click(screen.getByRole("button",{name:"Synthetic source"}));expect(review()).toBeEnabled();
  await user.click(review());expect(await screen.findByRole("textbox",{name:t("workingSummaryText")})).toHaveValue(f.context.draft_text);expect(contextReads).toBe(2);
});

it.each([false,true])("preserves the open source across a hidden desktop-to-compact breakpoint, desktopBack=%s",async desktopBack=>{
  const listeners=new Set<(event:{matches:boolean})=>void>();
  vi.stubGlobal("matchMedia",()=>({matches:false,media:"(max-width: 1080px)",addEventListener:(_:string,fn:(event:{matches:boolean})=>void)=>listeners.add(fn),removeEventListener:(_:string,fn:(event:{matches:boolean})=>void)=>listeners.delete(fn)}));
  const f=fixture(),user=userEvent.setup();
  const fetch=vi.spyOn(globalThis,"fetch").mockImplementation(async url=>String(url).includes("/working-summary?")?response({ok:true,context:f.context}):response({ok:false,code:"source_unavailable"},503));
  const library=(active:boolean)=><><button>Other page</button><div hidden={!active}><LiteratureLibrary sources={[f.record]} screenings={[]} t={t}
    onPrepare={vi.fn()} onScreen={vi.fn()} observationRead={{...f.scope,active}} pageSuspended={!active} onWorkingSummarySaved={f.onSaved}/></div></>;
  const {rerender}=render(library(true));
  // Open directly from the default desktop detail, without clicking its list row.
  await user.click(review());const input=await screen.findByRole("textbox",{name:t("workingSummaryText")});fireEvent.change(input,{target:{value:draft}});
  if(desktopBack)await user.click(screen.getByRole("button",{name:t("catalogBackToList")}));
  rerender(library(false));const outside=screen.getByRole("button",{name:"Other page"});outside.focus();const calls=fetch.mock.calls.length;
  act(()=>listeners.forEach(fn=>fn({matches:true})));
  expect(input).toBeInTheDocument();expect(input).not.toBeVisible();expect(outside).toHaveFocus();expect(fetch).toHaveBeenCalledTimes(calls);
  rerender(library(true));expect(screen.getByRole("textbox",{name:t("workingSummaryText")})).toBe(input);expect(input).toHaveValue(draft);expect(input).toBeVisible();
  expect(outside).toHaveFocus();expect(fetch.mock.calls.filter(call=>String(call[0]).includes("/working-summary"))).toHaveLength(1);
});

it("Cancel after returning discards only this draft and reopening requires a fresh context",async()=>{
  const f=fixture(),user=userEvent.setup();
  const fetch=vi.spyOn(globalThis,"fetch").mockImplementation(async()=>response({ok:true,context:f.context}));
  const {rerender}=render(<WorkingSummaryEditor {...props(f)}/>);
  await user.click(review());fireEvent.change(await screen.findByRole("textbox",{name:t("workingSummaryText")}),{target:{value:draft}});
  rerender(<WorkingSummaryEditor {...props(f)} scope={{...f.scope,active:false}} suspended/>);
  rerender(<WorkingSummaryEditor {...props(f)}/>);
  await user.click(screen.getByRole("button",{name:t("cancel")}));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();expect(review()).toHaveFocus();
  await user.click(review());expect(await screen.findByRole("textbox",{name:t("workingSummaryText")})).toHaveValue(f.context.draft_text);
  expect(fetch.mock.calls.map(call=>call[1]?.method)).toEqual(["GET","GET"]);
});

it.each(["ready","saving"] as const)("App Literature–Overview–Literature preserves %s draft and defers hidden save refresh",async stage=>{
  const f=fixture(),user=userEvent.setup(),pending=deferred();
  const project={id:"project-one",title:"Synthetic navigation",archetype:"review",goal:"Read selected material"};
  const workspace={ok:true,projects:[project],capabilities:{codex:{status:"unavailable",message:"Synthetic"},writing:{status:"unavailable",message:"Synthetic"},approval:{status:"unavailable",message:"Synthetic"}},protection_scope:"synthetic"};
  let contextReads=0,projectReads=0,posts=0;
  vi.spyOn(globalThis,"fetch").mockImplementation(async(url,init)=>{
    const path=String(url);
    if(path.endsWith("/workspace"))return response(workspace);
    if(path.endsWith("/projects/project-one")){projectReads++;return response({ok:true,project,records:[f.record],artifacts:[f.artifact],tasks:[],actions:[],manuscript:{authority_sources:[],contract:{}},workflow:null,warnings:[]});}
    if(path.endsWith("/artifacts/report-one/text"))return response({ok:false,code:"source_unavailable"},503);
    if(path.includes("/working-summary?")){contextReads++;return response({ok:true,context:{...f.context,revision:contextReads>1?freshRevision:revision}});}
    if(path.endsWith("/working-summary")&&init?.method==="POST"){
      posts++;expect(JSON.parse(String(init.body)).expected_revision).toBe(posts===1?revision:freshRevision);
      return stage==="saving"?pending.promise:response({ok:false,code:"stale_input"},400);
    }
    throw new Error("Unexpected synthetic request "+path);
  });
  window.history.replaceState({},"","#literature");render(<App/>);
  await user.click(await screen.findByRole("button",{name:`${t("workingSummaryReview")} report-one`}));
  const input=await screen.findByRole("textbox",{name:t("workingSummaryText")});fireEvent.change(input,{target:{value:draft}});
  if(stage==="saving")await user.click(screen.getByRole("button",{name:t("workingSummarySave")}));
  await user.click(screen.getByRole("link",{name:t("overview")}));
  await waitFor(()=>expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  const overview=screen.getByRole("heading",{name:t("overview"),level:1});await waitFor(()=>expect(overview).toHaveFocus());
  if(stage==="saving")await act(async()=>pending.resolve(savedResponse(f)));
  expect(overview).toHaveFocus();expect(window.location.hash).toBe("#overview");expect(projectReads).toBe(1);
  await user.click(screen.getByRole("link",{name:t("literature")}));
  await waitFor(()=>expect(input).toBeVisible());expect(screen.getByRole("textbox",{name:t("workingSummaryText")})).toBe(input);expect(input).toHaveValue(draft);
  expect(contextReads).toBe(1);expect(posts).toBe(stage==="saving"?1:0);
  if(stage==="saving")await waitFor(()=>expect(projectReads).toBe(2));
  else {
    await user.click(screen.getByRole("button",{name:t("workingSummarySave")}));await screen.findByText(t("workingSummaryStale"));
    expect(input).toHaveValue(draft);expect(screen.getByRole("button",{name:t("workingSummarySave")})).toBeDisabled();
    await user.click(screen.getByRole("button",{name:t("workingSummaryCheck")}));await screen.findByText(t("workingSummaryChecked"));
    expect(input).toHaveValue(draft);expect(contextReads).toBe(2);expect(posts).toBe(1);
    await user.click(screen.getByRole("button",{name:t("workingSummarySave")}));await waitFor(()=>expect(posts).toBe(2));
  }
});
