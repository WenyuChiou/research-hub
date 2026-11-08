import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SavedWorkingSummary, TaskWorkingSummaryEditor, workingSummary, type TaskProvenance } from "./WorkingSummaryEditor";
import { TaskCard } from "./Tasks";
import { translator } from "./i18n";
import type { Task } from "./types";

const t=translator("en"), hash=(c:string)=>c.repeat(64);
const response=(value:unknown,status=200)=>new Response(JSON.stringify(value),{status,headers:{"Content-Type":"application/json"}});
function fixture() {
  const provenance:TaskProvenance={kind:"abstract-task",version:1,project_id:"project-one",source_record_id:"fresh-source",task_id:"task-one",input_hash:hash("a"),action_hash:hash("b"),draft_sha256:hash("c")};
  const task:Task={id:provenance.task_id,project_id:provenance.project_id,operation:"paper-abstract-draft",mode:"handoff",status:"awaiting_human",action_hash:provenance.action_hash,
    request:{research_draft:{source_pack:{source_record_id:provenance.source_record_id,artifact_id:"original",source_sha256:hash("d"),text_sha256:hash("d"),text:"Synthetic source",start:0,end:16,source:{title:"Synthetic",locator:"synthetic:one",identity_status:"unverified",publication_version:"unknown"},scope:"abstract",scope_basis:"operator-selected range, not automatically verified",truncated:false}}},
    result:{status:"completed",semantic_acceptance:"pending",input_hash:provenance.input_hash,prose:"Generated candidate",artifacts:[{path:"proposals/task-one-123/draft.md",sha256:provenance.draft_sha256}]}};
  const context={source_record_id:provenance.source_record_id,provenance,revision:hash("e"),draft_text:"Generated candidate",working_summary:null as unknown};
  const saved={text:"My edited working prose",provenance,source_revision:hash("f"),previous_revision:context.revision,saved_at:"2026-11-06T10:00:00Z"};
  const record={id:provenance.source_record_id,kind:"source",data:{title:"Fresh source",human_acceptance:"pending",working_summary:saved}};
  return {provenance,task,context,saved,record,onSaved:vi.fn().mockResolvedValue(undefined)};
}
const opener=()=>screen.getByRole("button",{name:t("taskWorkingSummaryOpen")});
const save=()=>screen.getByRole("button",{name:t("workingSummarySave")});
const input=()=>screen.findByRole("textbox",{name:t("workingSummaryText")});
const props=(f:ReturnType<typeof fixture>)=>({task:f.task,t,onSaved:f.onSaved});


it.each(["en", "zh-TW"] as const)("protects an open summary from task cancellation (%s)", async locale => {
  const f=fixture(), tr=translator(locale), user=userEvent.setup();
  const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValue(response({ok:true,context:f.context}));
  render(<TaskCard {...props(f)} t={tr} approvalMessage="CLI"/>);
  const cancelTask=screen.getByRole("button",{name:tr("cancelTask")});
  expect(cancelTask).toBeEnabled();
  await user.click(screen.getByRole("button",{name:tr("taskWorkingSummaryOpen")}));
  const field=await screen.findByRole("textbox",{name:tr("workingSummaryText")});
  fireEvent.change(field,{target:{value:"Synthetic unsaved researcher prose"}});
  expect(cancelTask).toBeDisabled();
  await user.click(cancelTask);
  expect(field).toHaveValue("Synthetic unsaved researcher prose");
  expect(fetch).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole("button",{name:tr("cancel")}));
  expect(cancelTask).toBeEnabled();
  await user.click(cancelTask);
  expect(fetch.mock.calls[1][0]).toBe("/api/v1/tasks/task-one/cancel");
});

it("guards human decisions and repeated refreshes until the editor explicitly closes", async()=>{
  const f=fixture(),user=userEvent.setup();
  document.head.insertAdjacentHTML("beforeend", '<meta name="research-hub-human-token" content="synthetic-test-token">');
  const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValue(response({ok:true,context:f.context}));
  const view=render(<TaskCard {...props(f)} approvalMessage="CLI"/>);
  const decision=screen.getByRole("button",{name:t("recordDecision")});expect(decision).toBeEnabled();
  await user.click(opener());fireEvent.change(await input(),{target:{value:"Keep this edit"}});
  expect(decision).toBeDisabled();
  view.rerender(<TaskCard {...props(f)} task={{...f.task}} approvalMessage="CLI"/>);
  expect(decision).toBeDisabled();expect(await input()).toHaveValue("Keep this edit");
  // Even a programmatic form submit cannot bypass the ownership gate.
  fireEvent.submit(decision.closest("form")!);expect(fetch).toHaveBeenCalledTimes(1);
  await user.keyboard("{Escape}");expect(decision).toBeEnabled();
  await user.selectOptions(screen.getByRole("combobox",{name:new RegExp(t("outcome"))}),"accept");
  await user.type(screen.getByRole("textbox",{name:new RegExp(t("actor"))}),"Synthetic human");
  await user.type(screen.getByRole("textbox",{name:new RegExp(t("rationale"))}),"Reviewed synthetic result");
  await user.click(decision);expect(fetch.mock.calls[1][0]).toBe("/api/v1/tasks/task-one/decision");
});

it.each(["cancel","decision"])("does not open an editor during an already pending %s",async kind=>{
  const f=fixture(),user=userEvent.setup();let finish!:(r:Response)=>void;
  document.head.insertAdjacentHTML("beforeend", '<meta name="research-hub-human-token" content="synthetic-test-token">');
  const fetch=vi.spyOn(globalThis,"fetch").mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
  render(<TaskCard {...props(f)} approvalMessage="CLI"/>);
  if(kind==="cancel")await user.click(screen.getByRole("button",{name:t("cancelTask")}));
  else {
    await user.type(screen.getByRole("textbox",{name:new RegExp(t("actor"))}),"Synthetic human");
    await user.type(screen.getByRole("textbox",{name:new RegExp(t("rationale"))}),"Synthetic revision");
    await user.click(screen.getByRole("button",{name:t("recordDecision")}));
  }
  expect(opener()).toBeDisabled();await user.click(opener());expect(screen.queryByRole("dialog")).not.toBeInTheDocument();expect(fetch).toHaveBeenCalledTimes(1);
  await act(async()=>finish(response({ok:false,code:"stale_input",error:"Synthetic stale task"},409)));
  expect(opener()).toBeEnabled();
});

it.each([true,false])("keeps task actions gated during Save and after its outcome (%s)",async success=>{
  const f=fixture(),user=userEvent.setup();let finish!:(r:Response)=>void;
  const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context})).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
  const view=render(<TaskCard {...props(f)} approvalMessage="CLI"/>);await user.click(opener());fireEvent.change(await input(),{target:{value:f.saved.text}});await user.click(save());
  const cancelTask=screen.getByRole("button",{name:t("cancelTask")});expect(cancelTask).toBeDisabled();
  view.rerender(<TaskCard {...props(f)} task={{...f.task}} approvalMessage="CLI"/>);expect(cancelTask).toBeDisabled();
  await act(async()=>finish(success?response({ok:true,record:f.record}):response({ok:false,code:"stale_input",error:"Synthetic stale summary"},409)));
  expect(cancelTask).toBeDisabled();expect(await input()).toHaveValue(f.saved.text);expect(fetch).toHaveBeenCalledTimes(2);
  await user.click(screen.getByRole("button",{name:t(success?"workingSummaryClose":"cancel")}));expect(cancelTask).toBeEnabled();
});

it("releases an old session on changed task identity without locking other tasks",async()=>{
  const f=fixture(),user=userEvent.setup();vi.spyOn(globalThis,"fetch").mockResolvedValue(response({ok:true,context:f.context}));
  const view=render(<TaskCard {...props(f)} approvalMessage="CLI"/>);await user.click(opener());await input();
  view.rerender(<TaskCard {...props(f)} task={{...f.task,id:"task-two"}} approvalMessage="CLI"/>);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();expect(screen.getByRole("button",{name:t("cancelTask")})).toBeEnabled();
});

it.each([true,false])("keeps an unmounted same-task Save owned until it settles, without unlocking a newer editor (%s)",async success=>{
  const f=fixture(),user=userEvent.setup();let finish!:(r:Response)=>void;
  const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context}))
    .mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}))
    .mockResolvedValue(response({ok:true,context:{...f.context,provenance:{...f.provenance,action_hash:hash("1")}}}));
  const view=render(<TaskCard {...props(f)} approvalMessage="CLI"/>);
  await user.click(opener());fireEvent.change(await input(),{target:{value:f.saved.text}});await user.click(save());
  view.rerender(<TaskCard {...props(f)} task={{...f.task,action_hash:hash("1")}} approvalMessage="CLI"/>);
  const cancelTask=screen.getByRole("button",{name:t("cancelTask")});expect(cancelTask).toBeDisabled();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();await user.click(opener());await input();
  await act(async()=>finish(success?response({ok:true,record:f.record}):response({ok:false,code:"stale_input",error:"Synthetic old task revision"},409)));
  expect(cancelTask).toBeDisabled();expect(f.onSaved).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button",{name:t("cancel")}));expect(cancelTask).toBeEnabled();expect(fetch).toHaveBeenCalledTimes(3);
});

it("retains pending Save ownership after task becomes ineligible and releases it on settlement",async()=>{
  const f=fixture(),user=userEvent.setup();let finish!:(r:Response)=>void;
  vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context})).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
  const view=render(<TaskCard {...props(f)} approvalMessage="CLI"/>);await user.click(opener());await input();await user.click(save());
  view.rerender(<TaskCard {...props(f)} task={{...f.task,status:"awaiting_agent"}} approvalMessage="CLI"/>);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();expect(screen.getByRole("button",{name:t("cancelTask")})).toBeDisabled();
  await act(async()=>finish(response({ok:false,code:"stale_input",error:"Synthetic changed task"},409)));
  expect(screen.getByRole("button",{name:t("cancelTask")})).toBeEnabled();expect(f.onSaved).not.toHaveBeenCalled();
});
