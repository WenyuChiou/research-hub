import { StrictMode } from "react";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { TaskWorkingSummaryEditor, type TaskProvenance } from "./WorkingSummaryEditor";
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


it.each(["cancelled", "completed"] as const)("recovers exact raw edits when external status becomes %s", async status => {
  const f=fixture(), user=userEvent.setup(), raw="\ufeff  Synthetic unsaved researcher prose\u0085";
  const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValue(response({ok:true,context:f.context}));
  const view=render(<TaskCard {...props(f)} approvalMessage="CLI"/>);
  await user.click(opener());fireEvent.change(await input(),{target:{value:raw}});
  view.rerender(<TaskCard {...props(f)} task={{...f.task,status}} approvalMessage="CLI"/>);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  const recovery=screen.getByRole("region",{name:"Recovered working-summary edits"});
  const retained=within(recovery).getByRole("textbox",{name:"Retained text (read-only)"});
  expect(retained).toHaveValue(raw);expect(retained).toHaveAttribute("readonly");expect(retained).toBeEnabled();
  expect(within(recovery).queryByRole("button",{name:t("workingSummarySave")})).not.toBeInTheDocument();
  expect(within(recovery).queryByRole("button",{name:t("workingSummaryCheck")})).not.toBeInTheDocument();
  expect(recovery.textContent).toContain(JSON.stringify(f.provenance,null,2));
  expect(recovery.textContent).toContain(f.context.revision);
  expect(fetch.mock.calls.map(c=>c[1]?.method)).toEqual(["GET"]);expect(f.onSaved).not.toHaveBeenCalled();
});

it("retains old binding separately when a source/provenance refresh permits a fresh editor",async()=>{
  const f=fixture(),user=userEvent.setup(),raw="Old source edits";
  const nextProvenance={...f.provenance,source_record_id:"different-source",action_hash:hash("1")};
  const nextTask={...f.task,action_hash:nextProvenance.action_hash,request:{...f.task.request,research_draft:{...f.task.request!.research_draft!,source_pack:{...f.task.request!.research_draft!.source_pack,source_record_id:nextProvenance.source_record_id}}}};
  const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context}))
    .mockResolvedValue(response({ok:true,context:{...f.context,source_record_id:nextProvenance.source_record_id,provenance:nextProvenance,draft_text:"Fresh candidate"}}));
  const view=render(<TaskCard {...props(f)} approvalMessage="CLI"/>);await user.click(opener());fireEvent.change(await input(),{target:{value:raw}});
  view.rerender(<TaskCard {...props(f)} task={nextTask} approvalMessage="CLI"/>);
  const recovery=screen.getByRole("region",{name:"Recovered working-summary edits"});
  expect(within(recovery).getByRole("textbox")).toHaveValue(raw);expect(recovery.textContent).toContain(JSON.stringify(f.provenance,null,2));
  await user.click(opener());expect(await input()).toHaveValue("Fresh candidate");
  expect(fetch.mock.calls.map(c=>c[1]?.method)).toEqual(["GET","GET"]);expect(f.onSaved).not.toHaveBeenCalled();
});

it.each(["en","zh-TW"] as const)("labels recovery, retains raw text and explicitly discards it (%s)",async locale=>{
  const f=fixture(),tr=translator(locale),user=userEvent.setup();
  const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValue(response({ok:true,context:f.context}));
  const view=render(<TaskWorkingSummaryEditor {...props(f)} t={tr}/>);
  await user.click(screen.getByRole("button",{name:tr("taskWorkingSummaryOpen")}));
  fireEvent.change(await screen.findByRole("textbox",{name:tr("workingSummaryText")}),{target:{value:"Recovery only"}});
  view.rerender(<TaskWorkingSummaryEditor {...props(f)} t={tr} task={{...f.task,status:"cancelled"}}/>);
  const recovery=screen.getByRole("region",{name:tr("taskWorkingSummaryRecovery")});
  expect(within(recovery).getByText(tr("taskWorkingSummaryRecoveryHelp"))).toBeVisible();
  expect(within(recovery).getByText(tr("taskWorkingSummaryRecoveryLifetime"))).toBeVisible();
  const retained=within(recovery).getByRole("textbox",{name:tr("taskWorkingSummaryRetainedText")});
  retained.focus();expect(retained).toHaveFocus();expect(retained).toBeEnabled();
  await user.click(within(recovery).getByText(tr("taskWorkingSummaryOriginalBinding")));
  expect(within(recovery).getByText(f.context.revision)).toBeVisible();
  await user.click(within(recovery).getByRole("button",{name:tr("taskWorkingSummaryDiscardRecovery")}));
  expect(screen.queryByRole("region",{name:tr("taskWorkingSummaryRecovery")})).not.toBeInTheDocument();
  expect(fetch).toHaveBeenCalledTimes(1);expect(f.onSaved).not.toHaveBeenCalled();
});

it.each([["empty", ""], ["whitespace", " \u0085\u001c "], ["over-limit", "x".repeat(40001)]])("retains raw %s edits without normalization",async (_kind,raw)=>{
  const f=fixture(),user=userEvent.setup();vi.spyOn(globalThis,"fetch").mockResolvedValue(response({ok:true,context:f.context}));
  const view=render(<TaskWorkingSummaryEditor {...props(f)}/>);await user.click(opener());fireEvent.change(await input(),{target:{value:raw}});
  expect(save()).toBeDisabled();view.rerender(<TaskWorkingSummaryEditor {...props(f)} task={{...f.task,action_hash:hash("1")}}/>);
  expect(screen.getByRole("textbox",{name:t("taskWorkingSummaryRetainedText")})).toHaveValue(raw);
});

it.each(["untouched", "reverted", "cancel", "escape", "saved"])("does not create recovery after an %s session",async kind=>{
  const f=fixture(),user=userEvent.setup();
  const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context})).mockResolvedValue(response({ok:true,record:f.record}));
  const view=render(<TaskWorkingSummaryEditor {...props(f)}/>);await user.click(opener());const field=await input();
  if(kind!=="untouched")fireEvent.change(field,{target:{value:f.saved.text}});
  if(kind==="reverted")fireEvent.change(field,{target:{value:f.context.draft_text}});
  if(kind==="cancel")await user.click(screen.getByRole("button",{name:t("cancel")}));
  if(kind==="escape")await user.keyboard("{Escape}");
  if(kind==="saved"){await user.click(save());await screen.findByText(t("workingSummarySaved"));}
  view.rerender(<TaskWorkingSummaryEditor {...props(f)} task={{...f.task,status:"completed"}}/>);
  expect(screen.queryByRole("region",{name:t("taskWorkingSummaryRecovery")})).not.toBeInTheDocument();
  expect(fetch.mock.calls.map(c=>c[1]?.method)).toEqual(kind==="saved"?["GET","POST"]:["GET"]);
});

it("keeps repeated invalidations separate, including late save results and a newer editor",async()=>{
  const f=fixture(),user=userEvent.setup();let finish!:(r:Response)=>void;
  const bProvenance={...f.provenance,action_hash:hash("1")},bTask={...f.task,action_hash:hash("1")};
  const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context}))
    .mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}))
    .mockResolvedValue(response({ok:true,context:{...f.context,provenance:bProvenance,draft_text:"Candidate B"}}));
  const view=render(<TaskCard {...props(f)} approvalMessage="CLI"/>);
  await user.click(opener());fireEvent.change(await input(),{target:{value:f.saved.text}});await user.click(save());
  view.rerender(<TaskCard {...props(f)} task={bTask} approvalMessage="CLI"/>);
  expect(screen.getByRole("textbox",{name:t("taskWorkingSummaryRetainedText")})).toHaveValue(f.saved.text);
  await user.click(opener());fireEvent.change(await input(),{target:{value:"B unsaved raw"}});
  await act(async()=>finish(response({ok:true,record:f.record})));
  expect(f.onSaved).not.toHaveBeenCalled();expect(await input()).toHaveValue("B unsaved raw");
  expect(screen.getByRole("button",{name:t("cancelTask")})).toBeDisabled();
  view.rerender(<TaskCard {...props(f)} task={{...bTask,action_hash:hash("2")}} approvalMessage="CLI"/>);
  const recovered=screen.getAllByRole("region",{name:t("taskWorkingSummaryRecovery")});expect(recovered).toHaveLength(2);
  expect(within(recovered[0]).getByRole("textbox")).toHaveValue(f.saved.text);
  expect(within(recovered[1]).getByRole("textbox")).toHaveValue("B unsaved raw");
  expect(recovered[0].textContent).toContain(JSON.stringify(f.provenance,null,2));expect(recovered[1].textContent).toContain(JSON.stringify(bProvenance,null,2));
  expect(screen.getByRole("button",{name:t("cancelTask")})).toBeEnabled();
  await user.click(within(recovered[1]).getByRole("button",{name:t("taskWorkingSummaryDiscardRecovery")}));
  expect(screen.getByRole("textbox",{name:t("taskWorkingSummaryRetainedText")})).toHaveValue(f.saved.text);
  expect(fetch.mock.calls.map(c=>c[1]?.method)).toEqual(["GET","POST","GET"]);
});

it.each([true,false])("does not let a late same-provenance save settlement erase recovery or a newer edit (%s)",async success=>{
  const f=fixture(),user=userEvent.setup();let finish!:(r:Response)=>void;
  const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context}))
    .mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;})).mockResolvedValue(response({ok:true,context:f.context}));
  const view=render(<TaskCard {...props(f)} approvalMessage="CLI"/>);await user.click(opener());fireEvent.change(await input(),{target:{value:f.saved.text}});await user.click(save());
  view.rerender(<TaskCard {...props(f)} task={{...f.task,status:"awaiting_agent"}} approvalMessage="CLI"/>);
  view.rerender(<TaskCard {...props(f)} approvalMessage="CLI"/>);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();await user.click(opener());expect(await input()).toHaveValue(f.context.draft_text);
  fireEvent.change(await input(),{target:{value:"New same-binding draft"}});
  await act(async()=>finish(success?response({ok:true,record:f.record}):response({ok:false,code:"stale_input",error:"Synthetic stale"},409)));
  expect(f.onSaved).not.toHaveBeenCalled();expect(await input()).toHaveValue("New same-binding draft");
  expect(screen.getByRole("textbox",{name:t("taskWorkingSummaryRetainedText")})).toHaveValue(f.saved.text);
  await user.click(screen.getByRole("button",{name:t("cancel")}));
  expect(screen.getByRole("textbox",{name:t("taskWorkingSummaryRetainedText")})).toHaveValue(f.saved.text);
  expect(screen.getByRole("button",{name:t("cancelTask")})).toBeEnabled();expect(fetch).toHaveBeenCalledTimes(3);
});

it.each(["blocked","checking","earlier-saved"])("preserves newer raw edits from %s state without rearming recovery",async phase=>{
  const f=fixture(),user=userEvent.setup();let finish!:(r:Response)=>void;
  const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context})).mockRejectedValueOnce(new Error("Synthetic lost receipt"))
    .mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
  const view=render(<TaskWorkingSummaryEditor {...props(f)}/>);await user.click(opener());fireEvent.change(await input(),{target:{value:f.saved.text}});await user.click(save());await screen.findByText(t("workingSummaryUnknown"));
  if(phase!=="blocked")await user.click(screen.getByRole("button",{name:t("workingSummaryCheck")}));
  fireEvent.change(await input(),{target:{value:"\u0085New raw prose\ufeff"}});
  if(phase==="earlier-saved")await act(async()=>finish(response({ok:true,context:{...f.context,revision:hash("1"),working_summary:f.saved}})));
  view.rerender(<TaskWorkingSummaryEditor {...props(f)} task={{...f.task,action_hash:hash("2")}}/>);
  if(phase==="checking")await act(async()=>finish(response({ok:true,context:{...f.context,revision:hash("1"),working_summary:f.saved}})));
  expect(screen.getByRole("textbox",{name:t("taskWorkingSummaryRetainedText")})).toHaveValue("\u0085New raw prose\ufeff");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();expect(screen.queryByRole("button",{name:t("workingSummaryCheck")})).not.toBeInTheDocument();
  expect(f.onSaved).not.toHaveBeenCalled();expect(fetch.mock.calls.filter(c=>c[1]?.method==="POST")).toHaveLength(1);
});

it.each(["task","project"])("does not expose retained text under a different %s identity",async kind=>{
  const f=fixture(),user=userEvent.setup();vi.spyOn(globalThis,"fetch").mockResolvedValue(response({ok:true,context:f.context}));
  const view=render(<TaskWorkingSummaryEditor {...props(f)}/>);await user.click(opener());fireEvent.change(await input(),{target:{value:"Original private draft"}});
  view.rerender(<TaskWorkingSummaryEditor {...props(f)} task={{...f.task,...(kind==="task"?{id:"other-task"}:{project_id:"other-project"})}}/>);
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();expect(screen.queryByRole("region",{name:t("taskWorkingSummaryRecovery")})).not.toBeInTheDocument();
});

it("does not manufacture invalidation during StrictMode, same-binding refresh or inactive navigation",async()=>{
  const f=fixture(),user=userEvent.setup();
  const fetch=vi.spyOn(globalThis,"fetch").mockImplementation(async()=>response({ok:true,context:f.context}));
  const view=render(<StrictMode><TaskWorkingSummaryEditor {...props(f)}/></StrictMode>);
  await user.click(opener());fireEvent.change(await input(),{target:{value:"StrictMode draft"}});
  view.rerender(<StrictMode><TaskWorkingSummaryEditor {...props(f)} task={{...f.task}} active={false} onSaved={async()=>{}}/></StrictMode>);
  expect(screen.queryByRole("region",{name:t("taskWorkingSummaryRecovery")})).not.toBeInTheDocument();expect(save()).toBeDisabled();
  view.rerender(<StrictMode><TaskWorkingSummaryEditor {...props(f)}/></StrictMode>);
  expect(await input()).toHaveValue("StrictMode draft");expect(screen.queryByRole("region",{name:t("taskWorkingSummaryRecovery")})).not.toBeInTheDocument();
  view.rerender(<StrictMode><TaskWorkingSummaryEditor {...props(f)} task={{...f.task,status:"cancelled"}}/></StrictMode>);
  expect(screen.getAllByRole("region",{name:t("taskWorkingSummaryRecovery")})).toHaveLength(1);
  expect(screen.getByRole("textbox",{name:t("taskWorkingSummaryRetainedText")})).toHaveValue("StrictMode draft");
  expect(fetch.mock.calls.every(c=>c[1]?.method==="GET")).toBe(true);expect(f.onSaved).not.toHaveBeenCalled();
});

it.each([false,true])("retains a reversion to initial text after an earlier save attempt (receipt confirmed: %s)",async confirm=>{
  const f=fixture(),user=userEvent.setup();
  const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context})).mockRejectedValueOnce(new Error("Synthetic lost receipt"))
    .mockResolvedValue(response({ok:true,context:{...f.context,revision:hash("1"),working_summary:f.saved}}));
  const view=render(<TaskWorkingSummaryEditor {...props(f)}/>);await user.click(opener());fireEvent.change(await input(),{target:{value:f.saved.text}});await user.click(save());await screen.findByText(t("workingSummaryUnknown"));
  fireEvent.change(await input(),{target:{value:f.context.draft_text}});
  if(confirm){await user.click(screen.getByRole("button",{name:t("workingSummaryCheck")}));await screen.findByText(t("workingSummaryEarlierSaved"));}
  view.rerender(<TaskWorkingSummaryEditor {...props(f)} task={{...f.task,status:"cancelled"}}/>);
  expect(screen.getByRole("textbox",{name:t("taskWorkingSummaryRetainedText")})).toHaveValue(f.context.draft_text);
  expect(f.onSaved).not.toHaveBeenCalled();expect(fetch.mock.calls.filter(c=>c[1]?.method==="POST")).toHaveLength(1);
});
