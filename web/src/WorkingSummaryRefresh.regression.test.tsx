import App from "./App";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { WorkingSummaryEditor } from "./WorkingSummaryEditor";
import { translator } from "./i18n";
import type { ResearchRecord } from "./types";

const sha = "a".repeat(64);
const t = translator("en");
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), {status, headers:{"Content-Type":"application/json"}});
function fixture() {
  const record: ResearchRecord = {id:"source-one",kind:"source",data:{id:"one",title:"Synthetic source",summary:"Original saved prose",human_acceptance:"pending",source_records:[{observation_id:"obs-one",source_id:"one",work_id:"work-one",status:"available",evidence_level:"generated-summary",text_path:"report.md",text_sha256:sha}]}};
  const artifact = {id:"report-one",project_id:"project-one",source_record_id:record.id,path:"report.md",role:"evidence",sha256:sha,current:true};
  const context = {source_record_id:record.id,artifact_id:artifact.id,artifact_sha256:sha,revision:"1".repeat(64),draft_text:"Generated draft to edit",working_summary:null as null | Record<string, unknown>};
  const saved = {text:"My edited working summary",artifact_id:artifact.id,artifact_sha256:sha,source_revision:context.revision,previous_revision:context.revision,saved_at:"2026-11-03T00:00:00Z"};
  return {record,artifact,context,saved,scope:{projectId:"project-one",artifacts:[artifact],active:true},onSaved:vi.fn().mockResolvedValue(undefined)};
}
const props = (f: ReturnType<typeof fixture>) => ({record:f.record,scope:f.scope,t,onSaved:f.onSaved});
const review = () => screen.getByRole("button",{name:`${t("workingSummaryReview")} report-one`});


it.each(["ready", "blocked", "saving"] as const)("retains exact draft and request state across an identity-preserving Refresh while %s", async phase => {
  const f=fixture(), user=userEvent.setup();
  const draft="  Human unsaved work\n  ";
  let finish!:(r:Response)=>void;
  const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context}));
  if(phase==="blocked")fetch.mockRejectedValueOnce(new TypeError("Synthetic response loss"));
  if(phase==="saving")fetch.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
  const {rerender}=render(<WorkingSummaryEditor {...props(f)} scope={{...f.scope,revision:0}}/>);
  await user.click(review());
  const input=await screen.findByRole("textbox",{name:t("workingSummaryText")});
  fireEvent.change(input,{target:{value:draft}});
  if(phase!=="ready")await user.click(screen.getByRole("button",{name:t("workingSummarySave")}));
  if(phase==="blocked")await screen.findByText(t("workingSummaryUnknown"));
  rerender(<WorkingSummaryEditor {...props(f)} scope={{...f.scope,revision:1}}/>);
  expect(screen.getByRole("textbox",{name:t("workingSummaryText")})).toBe(input);
  expect(input).toHaveValue(draft);
  expect(fetch.mock.calls.map(call=>call[1]?.method)).toEqual(phase==="ready"?["GET"]:["GET","POST"]);
  if(phase==="blocked") {
    expect(screen.getByText(t("workingSummaryUnknown"))).toBeVisible();
    expect(screen.getByRole("button",{name:t("workingSummarySave")})).toBeDisabled();
    expect(screen.getByRole("button",{name:t("workingSummaryCheck")})).toBeEnabled();
  }
  if(phase==="saving") {
    expect(input).toBeDisabled();
    expect(screen.getByRole("button",{name:t("workingSummarySaving")})).toBeDisabled();
    await act(async()=>finish(response({ok:true,record:{...f.record,data:{...f.record.data,working_summary:{...f.saved,text:draft.trim()}}},reused:false})));
    await screen.findByText(t("workingSummarySaved"));
    expect(f.onSaved).toHaveBeenCalledOnce();
  }
});

it.each([false,true])("App Refresh retains selected working draft, with changed server revision=%s",async changed=>{
  const f=fixture(), user=userEvent.setup();
  const project={id:"project-one",title:"Synthetic refresh",archetype:"review",goal:"Read selected material"};
  const workspace={ok:true,projects:[project],capabilities:{codex:{status:"unavailable",message:"Synthetic"},writing:{status:"unavailable",message:"Synthetic"},approval:{status:"unavailable",message:"Synthetic"}},protection_scope:"synthetic"};
  const draft="  Preserve my exact human draft\n  ";
  let projectReads=0,contextReads=0,posts=0;
  const freshRevision="2".repeat(64);
  const fetch=vi.spyOn(globalThis,"fetch").mockImplementation(async(url,init)=>{
    const path=String(url);
    if(path.endsWith("/workspace"))return response(workspace);
    if(path.endsWith("/projects/project-one")) {
      projectReads++;
      return response({ok:true,project,records:[{...f.record,data:{...f.record.data,...(changed&&projectReads>1?{relevance:"Changed server metadata"}:{})}}],artifacts:[f.artifact],tasks:[],actions:[],manuscript:{authority_sources:[],contract:{}},workflow:null,warnings:[]});
    }
    if(path.endsWith("/artifacts/report-one/text"))return response({ok:false,error:"Synthetic unavailable preview",code:"source_unavailable"},503);
    if(path.includes("/working-summary?")) {
      contextReads++;
      return response({ok:true,context:{...f.context,revision:changed&&contextReads>1?freshRevision:f.context.revision}});
    }
    if(path.endsWith("/working-summary")&&init?.method==="POST") {
      posts++;
      const body=JSON.parse(String(init.body));
      if(posts===1){expect(body.expected_revision).toBe(f.context.revision);return response({ok:false,error:"Synthetic revision changed",code:"stale_input"},400);}
      expect(body.expected_revision).toBe(freshRevision);
      expect(body.text).toBe(draft.trim());
      return response({ok:true,record:{...f.record,data:{...f.record.data,working_summary:{...f.saved,text:draft.trim(),previous_revision:freshRevision}}},reused:false});
    }
    throw new Error("Unexpected synthetic request "+path);
  });
  window.history.replaceState({},"","#literature");render(<App/>);
  await user.click(await screen.findByRole("button",{name:`${t("workingSummaryReview")} report-one`}));
  const input=await screen.findByRole("textbox",{name:t("workingSummaryText")});
  fireEvent.change(input,{target:{value:draft}});
  await user.click(screen.getByRole("button",{name:"Refresh"}));
  await waitFor(()=>expect(projectReads).toBe(2));
  expect(screen.getByRole("textbox",{name:t("workingSummaryText")})).toBe(input);
  expect(input).toHaveValue(draft);
  expect(contextReads).toBe(1);expect(posts).toBe(0);
  if(changed){
    await user.click(screen.getByRole("button",{name:t("workingSummarySave")}));
    await screen.findByText(t("workingSummaryStale"));
    expect(input).toHaveValue(draft);
    expect(screen.getByRole("button",{name:t("workingSummarySave")})).toBeDisabled();
    await user.click(screen.getByRole("button",{name:t("workingSummaryCheck")}));
    await screen.findByText(t("workingSummaryChecked"));
    expect(input).toHaveValue(draft);expect(posts).toBe(1);
    await user.click(screen.getByRole("button",{name:t("workingSummarySave")}));
    await waitFor(()=>expect(posts).toBe(2));
    await waitFor(()=>expect(screen.getByRole("button",{name:t("workingSummaryClose")})).toBeEnabled());
    expect(contextReads).toBe(2);
  }
  expect(fetch.mock.calls.filter(call=>call[1]?.method==="POST")).toHaveLength(changed?2:0);
});
