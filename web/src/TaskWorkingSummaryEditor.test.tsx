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

describe.each(["en","zh-TW"] as const)("task-bound working summary %s",locale=>{
  it("opens only by explicit action and saves exact task provenance without accepting or rewriting the candidate",async()=>{
    const f=fixture(), tr=translator(locale),user=userEvent.setup(), before=JSON.stringify(f.task);
    const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context})).mockResolvedValueOnce(response({ok:true,record:f.record,reused:false}));
    render(<TaskCard {...props(f)} t={tr} approvalMessage="Human approval unavailable" onSaved={f.onSaved}/>);
    expect(fetch).not.toHaveBeenCalled(); expect(screen.getAllByText(tr("taskWorkingSummaryPending")).length).toBe(1);
    const button=screen.getByRole("button",{name:tr("taskWorkingSummaryOpen")});button.focus();await user.keyboard("{Enter}");
    const field=await screen.findByRole("textbox",{name:tr("workingSummaryText")});expect(field).toHaveValue(f.context.draft_text);expect(field).toHaveFocus();
    fireEvent.change(field,{target:{value:f.saved.text}});await user.click(screen.getByRole("button",{name:tr("workingSummarySave")}));
    await screen.findByText(tr("workingSummarySaved"));
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/projects/project-one/working-summary?source_record_id=fresh-source&task_id=task-one");
    expect(JSON.parse(String(fetch.mock.calls[1][1]?.body))).toEqual({source_record_id:"fresh-source",task_id:"task-one",provenance:f.provenance,expected_revision:f.context.revision,text:f.saved.text});
    expect(fetch).toHaveBeenCalledTimes(2);expect(f.onSaved).toHaveBeenCalledTimes(1);expect(JSON.stringify(f.task)).toBe(before);
    expect(f.record.data).not.toHaveProperty("id");expect(f.record.data).not.toHaveProperty("source_records");
  });
});

it("Cancel and Escape never save, return focus and reopen fresh context",async()=>{
  const f=fixture(),user=userEvent.setup(),fetch=vi.spyOn(globalThis,"fetch").mockImplementation(async()=>response({ok:true,context:f.context}));
  render(<TaskWorkingSummaryEditor {...props(f)}/>);await user.click(opener());fireEvent.change(await input(),{target:{value:"Unsaved"}});await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();expect(opener()).toHaveFocus();await user.click(opener());expect(await input()).toHaveValue(f.context.draft_text);
  await user.click(screen.getByRole("button",{name:t("cancel")}));expect(fetch.mock.calls.every(c=>c[1]?.method==="GET")).toBe(true);expect(f.onSaved).not.toHaveBeenCalled();
});

it.each(["project_id","source_record_id","task_id","action_hash","input_hash","draft_sha256","kind","version","extra"])("rejects foreign or malformed context provenance: %s",async field=>{
  const f=fixture();const provenance={...f.provenance,[field]:field==="version"?2:"foreign"};
  vi.spyOn(globalThis,"fetch").mockResolvedValue(response({ok:true,context:{...f.context,provenance}}));
  render(<TaskWorkingSummaryEditor {...props(f)}/>);await userEvent.click(opener());await screen.findByText(t("workingSummaryLoadFailed"));expect(save()).toBeDisabled();expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
});
it.each(["source","artifact","saved"])("rejects mismatched context envelope: %s",async field=>{
  const f=fixture();const context={...f.context,...(field==="source"?{source_record_id:"foreign"}:field==="artifact"?{artifact_id:"fake"}:{working_summary:{...f.saved,provenance:{...f.provenance,version:2}}})};
  vi.spyOn(globalThis,"fetch").mockResolvedValue(response({ok:true,context}));render(<TaskWorkingSummaryEditor {...props(f)}/>);await userEvent.click(opener());await screen.findByText(t("workingSummaryLoadFailed"));expect(save()).toBeDisabled();
});

it.each([false,true])("reopens matching saved prose only when candidate matches (%s)",async foreign=>{
  const f=fixture();f.context.working_summary={...f.saved,provenance:{...f.provenance,task_id:foreign?"other":f.provenance.task_id}};
  vi.spyOn(globalThis,"fetch").mockResolvedValue(response({ok:true,context:f.context}));render(<TaskWorkingSummaryEditor {...props(f)}/>);await userEvent.click(opener());expect(await input()).toHaveValue(foreign?f.context.draft_text:f.saved.text);
});

it("retains edits over refresh and navigation, with no hidden actions or focus stealing",async()=>{
  const f=fixture(),user=userEvent.setup(),fetch=vi.spyOn(globalThis,"fetch").mockResolvedValue(response({ok:true,context:f.context}));
  const view=render(<><button>Other page</button><TaskWorkingSummaryEditor {...props(f)}/></>);await user.click(opener());const field=await input();fireEvent.change(field,{target:{value:"Keep unsaved"}});
  view.rerender(<><button>Other page</button><TaskWorkingSummaryEditor {...props(f)} task={{...f.task}}/></>);expect(field).toHaveValue("Keep unsaved");
  const outside=screen.getByRole("button",{name:"Other page"});outside.focus();view.rerender(<><button>Other page</button><TaskWorkingSummaryEditor {...props(f)} active={false}/></>);
  expect(save()).toBeDisabled();fireEvent.click(save());expect(fetch).toHaveBeenCalledTimes(1);expect(outside).toHaveFocus();
  view.rerender(<><button>Other page</button><TaskWorkingSummaryEditor {...props(f)}/></>);expect(await input()).toHaveValue("Keep unsaved");expect(fetch).toHaveBeenCalledTimes(1);
});

it("changed task identity dismisses old edits and fences a late read",async()=>{
  const f=fixture();let resolve!:(r:Response)=>void;
  vi.spyOn(globalThis,"fetch").mockImplementation(()=>new Promise(r=>{resolve=r;}));
  const view=render(<TaskWorkingSummaryEditor {...props(f)}/>);await userEvent.click(opener());view.rerender(<TaskWorkingSummaryEditor {...props(f)} task={{...f.task,action_hash:hash("1")}}/>);
  await act(async()=>resolve(response({ok:true,context:f.context})));expect(screen.queryByRole("dialog")).not.toBeInTheDocument();expect(f.onSaved).not.toHaveBeenCalled();
});

it("holds unknown saves until a read confirms the exact receipt, never repeats writes",async()=>{
  const f=fixture(),user=userEvent.setup();const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context})).mockRejectedValueOnce(new Error("lost response")).mockResolvedValueOnce(response({ok:true,context:{...f.context,working_summary:f.saved}}));
  render(<TaskWorkingSummaryEditor {...props(f)}/>);await user.click(opener());fireEvent.change(await input(),{target:{value:f.saved.text}});await user.click(save());await screen.findByText(t("workingSummaryUnknown"));expect(save()).toBeDisabled();
  await user.click(screen.getByRole("button",{name:t("workingSummaryCheck")}));await screen.findByText(t("workingSummarySaved"));expect(fetch.mock.calls.filter(c=>c[1]?.method==="POST")).toHaveLength(1);expect(f.onSaved).toHaveBeenCalledTimes(1);
});

it("a foreign save receipt cannot confirm success and blocked drafts survive",async()=>{
  const f=fixture();vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context})).mockResolvedValueOnce(response({ok:true,record:{...f.record,data:{...f.record.data,working_summary:{...f.saved,provenance:{...f.provenance,task_id:"foreign"}}}}}));
  render(<TaskWorkingSummaryEditor {...props(f)}/>);await userEvent.click(opener());fireEvent.change(await input(),{target:{value:f.saved.text}});await userEvent.click(save());await screen.findByText(t("workingSummaryUnknown"));expect(await input()).toHaveValue(f.saved.text);expect(f.onSaved).not.toHaveBeenCalled();
});

it("blocks stale writes and oversized prose without truncation",async()=>{
  const f=fixture();const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context})).mockResolvedValueOnce(response({ok:false,code:"stale_input",error:"Changed"},409));
  render(<TaskWorkingSummaryEditor {...props(f)}/>);await userEvent.click(opener());const field=await input();fireEvent.change(field,{target:{value:"x".repeat(40001)}});expect(save()).toBeDisabled();expect(field).toHaveValue("x".repeat(40001));
  fireEvent.change(field,{target:{value:f.saved.text}});await userEvent.click(save());await screen.findByText(t("workingSummaryStale"));expect(save()).toBeDisabled();expect(field).toHaveValue(f.saved.text);expect(fetch).toHaveBeenCalledTimes(2);
});

it("does not duplicate rapid saves and defers refresh while page is hidden",async()=>{
  const f=fixture();let resolve!:(r:Response)=>void;const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context})).mockImplementationOnce(()=>new Promise(r=>{resolve=r;}));
  const view=render(<TaskWorkingSummaryEditor {...props(f)}/>);await userEvent.click(opener());fireEvent.change(await input(),{target:{value:f.saved.text}});const button=save();fireEvent.click(button);fireEvent.click(button);expect(fetch).toHaveBeenCalledTimes(2);
  view.rerender(<TaskWorkingSummaryEditor {...props(f)} active={false}/>);await act(async()=>resolve(response({ok:true,record:f.record})));expect(f.onSaved).not.toHaveBeenCalled();
  view.rerender(<TaskWorkingSummaryEditor {...props(f)}/>);await waitFor(()=>expect(f.onSaved).toHaveBeenCalledTimes(1));
});

it.each(["duplicate","missing","accepted","other-operation"])("does not offer an ambiguous or ineligible candidate: %s",kind=>{
  const f=fixture(),result=f.task.result as {artifacts:unknown[]};
  if(kind==="duplicate")result.artifacts.push({...result.artifacts[0] as object});if(kind==="missing")result.artifacts=[];if(kind==="accepted")f.task.status="completed";if(kind==="other-operation")f.task.operation="draft";
  render(<TaskWorkingSummaryEditor {...props(f)}/>);expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

it("renders task-based working prose beside source without legacy IDs and rejects foreign source provenance",()=>{
  const f=fixture();render(<SavedWorkingSummary record={f.record} t={t}/>);expect(screen.getByText(f.saved.text)).toBeVisible();expect(workingSummary({...f.record,id:"foreign"})).toBeUndefined();
});

// Integration with #251: task-provenance receipts use the same Python-compatible
// text normalization as legacy observations, without changing raw local edits.
describe.each(["en","zh-TW"] as const)("task Unicode normalization %s",locale=>{
  const tr=translator(locale);
  const open=()=>screen.getByRole("button",{name:tr("taskWorkingSummaryOpen")});
  const submit=()=>screen.getByRole("button",{name:tr("workingSummarySave")});
  const field=()=>screen.findByRole("textbox",{name:tr("workingSummaryText")});

  it.each(["\ufeffWorking prose\ufeff","\ufeff", "\ufeff\u0085Working prose\u001c\ufeff"])("preserves U+FEFF in exact task save receipts: %j",async raw=>{
    const f=fixture(),user=userEvent.setup(),saved={...f.saved,text:raw};
    const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context}))
      .mockResolvedValueOnce(response({ok:true,record:{...f.record,data:{...f.record.data,working_summary:saved}},reused:false}));
    render(<TaskWorkingSummaryEditor {...props(f)} t={tr}/>);await user.click(open());
    const textarea=await field();fireEvent.change(textarea,{target:{value:raw}});expect(submit()).toBeEnabled();await user.click(submit());
    await screen.findByText(tr("workingSummarySaved"));expect(textarea).toHaveValue(raw);
    expect(JSON.parse(String(fetch.mock.calls[1][1]?.body))).toEqual({source_record_id:f.provenance.source_record_id,task_id:f.provenance.task_id,
      provenance:f.provenance,expected_revision:f.context.revision,text:raw});
    expect(f.onSaved).toHaveBeenCalledTimes(1);expect(fetch.mock.calls.map(c=>c[1]?.method)).toEqual(["GET","POST"]);
  });

  it("reopens a U+FEFF-only persisted task summary without rejecting its provenance receipt",async()=>{
    const f=fixture(),saved={...f.saved,text:"\ufeff"};f.context.working_summary=saved;
    const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValue(response({ok:true,context:f.context}));
    render(<TaskWorkingSummaryEditor {...props(f)} t={tr}/>);await userEvent.click(open());expect(await field()).toHaveValue("\ufeff");expect(submit()).toBeEnabled();
    expect(workingSummary({...f.record,data:{...f.record.data,working_summary:saved}})).toEqual(saved);expect(fetch).toHaveBeenCalledTimes(1);
  });

  it.each(["\u0085","\u001c","\u001d","\u001e","\u001f"])("trims Python edge whitespace %j but preserves raw task edits",async whitespace=>{
    const f=fixture(),user=userEvent.setup(),raw=whitespace+f.saved.text+whitespace;
    const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context})).mockResolvedValueOnce(response({ok:true,record:f.record,reused:false}));
    render(<TaskWorkingSummaryEditor {...props(f)} t={tr}/>);await user.click(open());const textarea=await field();fireEvent.change(textarea,{target:{value:raw}});
    expect(textarea).toHaveValue(raw);await user.click(submit());await screen.findByText(tr("workingSummarySaved"));expect(textarea).toHaveValue(raw);
    expect(JSON.parse(String(fetch.mock.calls[1][1]?.body))).toEqual({source_record_id:f.provenance.source_record_id,task_id:f.provenance.task_id,
      provenance:f.provenance,expected_revision:f.context.revision,text:f.saved.text});expect(f.onSaved).toHaveBeenCalledTimes(1);
  });

  it.each(["\u0085","\u001c","\u001d","\u001e","\u001f","\u0085\u001c\u001d\u001e\u001f\r\n"])("rejects only-whitespace task edits without a POST: %j",async raw=>{
    const f=fixture(),fetch=vi.spyOn(globalThis,"fetch").mockResolvedValue(response({ok:true,context:f.context}));
    render(<TaskWorkingSummaryEditor {...props(f)} t={tr}/>);await userEvent.click(open());const textarea=await field();fireEvent.change(textarea,{target:{value:raw}});
    expect(submit()).toBeDisabled();fireEvent.click(submit());expect(textarea).toHaveValue(raw.replace(/\r\n/g,"\n"));expect(fetch).toHaveBeenCalledTimes(1);expect(f.onSaved).not.toHaveBeenCalled();
  });

  it("normalizes CRLF and outer Python whitespace without altering internal whitespace or task identity",async()=>{
    const f=fixture(),raw="\u0085\r\nFirst\r\n\ufeff\u001cinside\r\nLast\u001f",normalized="First\n\ufeff\u001cinside\nLast";
    const saved={...f.saved,text:normalized},fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context}))
      .mockResolvedValueOnce(response({ok:true,record:{...f.record,data:{...f.record.data,working_summary:saved}},reused:false}));
    render(<TaskWorkingSummaryEditor {...props(f)} t={tr}/>);await userEvent.click(open());const textarea=await field();fireEvent.change(textarea,{target:{value:raw}});
    // HTML textarea canonicalizes CRLF to LF before React receives onChange.
    const localValue=(textarea as HTMLTextAreaElement).value;expect(localValue).toBe(raw.replace(/\r\n/g,"\n"));
    await userEvent.click(submit());await screen.findByText(tr("workingSummarySaved"));expect(textarea).toHaveValue(localValue);
    expect(JSON.parse(String(fetch.mock.calls[1][1]?.body))).toEqual({source_record_id:f.provenance.source_record_id,task_id:f.provenance.task_id,
      provenance:f.provenance,expected_revision:f.context.revision,text:normalized});
  });

  it.each([false,true])("reconciles a lost normalized task save while retaining newer edits (%s)",async newerEdits=>{
    const f=fixture(),user=userEvent.setup(),raw="\u0085\ufeffWorking\r\nprose\ufeff\u001c",normalized="\ufeffWorking\nprose\ufeff",newer="\u001f\ufeffNew unsaved text\u0085";
    const saved={...f.saved,text:normalized};
    let finishCheck!:(value:Response)=>void;
    const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context}))
      .mockRejectedValueOnce(new Error("Synthetic lost response after commit"))
      .mockImplementationOnce(()=>new Promise(resolve=>{finishCheck=resolve;}));
    render(<TaskWorkingSummaryEditor {...props(f)} t={tr}/>);await user.click(open());const textarea=await field();fireEvent.change(textarea,{target:{value:raw}});await user.click(submit());
    await screen.findByText(tr("workingSummaryUnknown"));expect(textarea).toHaveValue(raw.replace(/\r\n/g,"\n"));expect(submit()).toBeDisabled();
    await user.click(screen.getByRole("button",{name:tr("workingSummaryCheck")}));
    if(newerEdits)fireEvent.change(textarea,{target:{value:newer}});
    await act(async()=>finishCheck(response({ok:true,context:{...f.context,revision:hash("1"),working_summary:saved}})));
    await screen.findByText(tr(newerEdits?"workingSummaryEarlierSaved":"workingSummarySaved"));
    expect(textarea).toHaveValue(newerEdits?newer:raw.replace(/\r\n/g,"\n"));expect(f.onSaved).toHaveBeenCalledTimes(newerEdits?0:1);
    expect(JSON.parse(String(fetch.mock.calls[1][1]?.body))).toEqual({source_record_id:f.provenance.source_record_id,task_id:f.provenance.task_id,
      provenance:f.provenance,expected_revision:f.context.revision,text:normalized});
    expect(fetch.mock.calls.map(c=>c[1]?.method)).toEqual(["GET","POST","GET"]);if(newerEdits)expect(submit()).toBeEnabled();
  });
  it("preserves lone CR and interior separators from task draft state while normalizing CRLF",async()=>{
    const f=fixture(),raw="\u0085First\r\nSecond\rThird\u001cinside\ufeff\u001f",normalized="First\nSecond\rThird\u001cinside\ufeff";
    f.context.draft_text=raw;
    const saved={...f.saved,text:normalized},fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context}))
      .mockResolvedValueOnce(response({ok:true,record:{...f.record,data:{...f.record.data,working_summary:saved}},reused:false}));
    render(<TaskWorkingSummaryEditor {...props(f)} t={tr}/>);await userEvent.click(open());await field();await userEvent.click(submit());
    await screen.findByText(tr("workingSummarySaved"));expect(JSON.parse(String(fetch.mock.calls[1][1]?.body)).text).toBe(normalized);
    expect(f.onSaved).toHaveBeenCalledTimes(1);
  });

  it("rejects the wrong task provenance hash even when normalized save text matches",async()=>{
    const f=fixture(),raw="\u0085"+f.saved.text+"\u001f";
    const foreign={...f.saved,provenance:{...f.provenance,draft_sha256:hash("2")}};
    const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context}))
      .mockResolvedValueOnce(response({ok:true,record:{...f.record,data:{...f.record.data,working_summary:foreign}},reused:false}));
    render(<TaskWorkingSummaryEditor {...props(f)} t={tr}/>);await userEvent.click(open());const textarea=await field();fireEvent.change(textarea,{target:{value:raw}});await userEvent.click(submit());
    await screen.findByText(tr("workingSummaryUnknown"));expect(textarea).toHaveValue(raw);expect(submit()).toBeDisabled();expect(f.onSaved).not.toHaveBeenCalled();
    expect(JSON.parse(String(fetch.mock.calls[1][1]?.body))).toMatchObject({text:f.saved.text,provenance:f.provenance});expect(fetch).toHaveBeenCalledTimes(2);
  });

});
