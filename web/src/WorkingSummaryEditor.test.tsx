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

describe.each(["en","zh-TW"] as const)("working summary review %s",locale => {
  it("loads only explicitly selected artifact, edits and saves the exact bound context", async () => {
    const f=fixture(), tr=translator(locale), user=userEvent.setup(), before=JSON.stringify(f.record);
    const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context})).mockResolvedValueOnce(response({ok:true,record:{...f.record,data:{...f.record.data,working_summary:f.saved}},reused:false}));
    render(<WorkingSummaryEditor {...props(f)} t={tr}/>);
    expect(fetch).not.toHaveBeenCalled();
    const button=screen.getByRole("button",{name:`${tr("workingSummaryReview")} report-one`});
    button.focus(); await user.keyboard("{Enter}");
    const input=await screen.findByRole("textbox",{name:tr("workingSummaryText")});
    expect(input).toHaveFocus(); expect(input).toHaveValue(f.context.draft_text);
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/projects/project-one/working-summary?source_record_id=source-one&artifact_id=report-one");
    await user.clear(input);await user.type(input,f.saved.text);await user.click(screen.getByRole("button",{name:tr("workingSummarySave")}));
    await screen.findByText(tr("workingSummarySaved"));
    expect(JSON.parse(String(fetch.mock.calls[1][1]?.body))).toEqual({source_record_id:f.record.id,artifact_id:f.artifact.id,artifact_sha256:sha,expected_revision:f.context.revision,text:f.saved.text});
    expect(f.onSaved).toHaveBeenCalledTimes(1);expect(JSON.stringify(f.record)).toBe(before);
  });
});

it("cancels without POST and returns focus; reopens with a fresh context",async()=>{
  const f=fixture(),user=userEvent.setup(),fetch=vi.spyOn(globalThis,"fetch").mockImplementation(async()=>response({ok:true,context:f.context}));
  render(<WorkingSummaryEditor {...props(f)}/>);await user.click(review());
  await user.type(await screen.findByRole("textbox",{name:t("workingSummaryText")}),"unsaved");
  await user.keyboard("{Escape}");expect(screen.queryByRole("dialog")).not.toBeInTheDocument();expect(review()).toHaveFocus();
  expect(fetch.mock.calls.every(call=>call[1]?.method==="GET")).toBe(true);
  await user.click(review());expect(await screen.findByRole("textbox",{name:t("workingSummaryText")})).toHaveValue(f.context.draft_text);
});

it("requires explicit artifact choice and never prepopulates another artifact's working text",async()=>{
  const f=fixture(), user=userEvent.setup();
  f.scope.artifacts.push({...f.artifact,id:"report-two",path:"report-two.md",sha256:"b".repeat(64)});
  (f.record.data.source_records as Record<string,unknown>[]).push({observation_id:"obs-two",source_id:"one",work_id:"work-one",status:"available",evidence_level:"generated-summary",text_path:"report-two.md",text_sha256:"b".repeat(64)});
  f.context.working_summary={...f.saved,artifact_id:"report-two",artifact_sha256:"b".repeat(64)};
  const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValue(response({ok:true,context:f.context}));
  render(<WorkingSummaryEditor {...props(f)}/>);expect(fetch).not.toHaveBeenCalled();
  expect(screen.getByRole("button",{name:`${t("workingSummaryReview")} report-two`})).toBeVisible();
  await user.click(review());expect(await screen.findByRole("textbox",{name:t("workingSummaryText")})).toHaveValue(f.context.draft_text);
});

it("prepopulates saved working text only for the same artifact and hash",async()=>{
  const f=fixture();f.context.working_summary=f.saved;
  vi.spyOn(globalThis,"fetch").mockResolvedValue(response({ok:true,context:f.context}));
  render(<WorkingSummaryEditor {...props(f)}/>);await userEvent.click(review());
  expect(await screen.findByRole("textbox",{name:t("workingSummaryText")})).toHaveValue(f.saved.text);
});

it.each([400,409])("keeps edits on HTTP %s stale rejection, redacts errors and requires explicit context reload",async status=>{
  const f=fixture(),user=userEvent.setup();
  const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context})).mockResolvedValueOnce(response({ok:false,error:"C:/private/source.md",code:"stale_input"},status)).mockResolvedValueOnce(response({ok:true,context:{...f.context,revision:"2".repeat(64)}}));
  render(<WorkingSummaryEditor {...props(f)}/>);await user.click(review());const input=await screen.findByRole("textbox",{name:t("workingSummaryText")});
  await user.clear(input);await user.type(input,"Keep my edit");await user.click(screen.getByRole("button",{name:t("workingSummarySave")}));
  expect(await screen.findByText(t("workingSummaryStale"))).toBeVisible();expect(input).toHaveValue("Keep my edit");expect(screen.queryByText("C:/private/source.md")).not.toBeInTheDocument();
  expect(screen.getByRole("button",{name:t("workingSummarySave")})).toBeDisabled();
  await user.click(screen.getByRole("button",{name:t("workingSummaryCheck")}));
  await waitFor(()=>expect(screen.getByRole("button",{name:t("workingSummarySave")})).toBeEnabled());expect(input).toHaveValue("Keep my edit");expect(fetch).toHaveBeenCalledTimes(3);
});

it("checks uncertain POST outcome with GET before permitting another save and confirms a persisted match",async()=>{
  const f=fixture(),user=userEvent.setup();
  const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context})).mockRejectedValueOnce(new TypeError("transport disconnected")).mockResolvedValueOnce(response({ok:true,context:{...f.context,revision:"2".repeat(64),working_summary:f.saved}}));
  render(<WorkingSummaryEditor {...props(f)}/>);await user.click(review());const input=await screen.findByRole("textbox",{name:t("workingSummaryText")});
  await user.clear(input);await user.type(input,f.saved.text);await user.click(screen.getByRole("button",{name:t("workingSummarySave")}));
  expect(await screen.findByText(t("workingSummaryUnknown"))).toBeVisible();expect(input).toHaveValue(f.saved.text);expect(screen.getByRole("button",{name:t("workingSummarySave")})).toBeDisabled();
  await user.click(screen.getByRole("button",{name:t("workingSummaryCheck")}));await screen.findByText(t("workingSummarySaved"));
  expect(fetch.mock.calls.map(c=>c[1]?.method)).toEqual(["GET","POST","GET"]);expect(f.onSaved).toHaveBeenCalledOnce();expect(screen.getByRole("button",{name:t("workingSummarySave")})).toBeDisabled();
});

it("keeps uncertain state blocked when the saved-state GET fails",async()=>{
  const f=fixture(),user=userEvent.setup();
  const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context})).mockRejectedValueOnce(new TypeError("offline")).mockRejectedValueOnce(new TypeError("offline"));
  render(<WorkingSummaryEditor {...props(f)}/>);await user.click(review());await screen.findByRole("textbox",{name:t("workingSummaryText")});await user.click(screen.getByRole("button",{name:t("workingSummarySave")}));
  await screen.findByText(t("workingSummaryUnknown"));await user.click(screen.getByRole("button",{name:t("workingSummaryCheck")}));await screen.findByText(t("workingSummaryCheckFailed"));
  expect(screen.getByRole("button",{name:t("workingSummarySave")})).toBeDisabled();expect(fetch).toHaveBeenCalledTimes(3);
});

describe.each(["en","zh-TW"] as const)("forbidden working-summary recovery %s",locale=>{
  it.each(["save","check"] as const)("retains unsent edits and gives safe manual recovery after forbidden %s",async stage=>{
    const f=fixture(),tr=translator(locale),user=userEvent.setup(),before=JSON.stringify(f.record);
    const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context}));
    if(stage==="save")fetch.mockResolvedValueOnce(response({ok:false,code:"forbidden",error:"Untrusted request"},403));
    else fetch.mockRejectedValueOnce(new TypeError("Synthetic lost outcome"))
      .mockResolvedValueOnce(response({ok:false,code:"forbidden",error:"Untrusted origin"},403));
    render(<WorkingSummaryEditor {...props(f)} t={tr}/>);
    await user.click(screen.getByRole("button",{name:`${tr("workingSummaryReview")} report-one`}));
    const input=await screen.findByRole("textbox",{name:tr("workingSummaryText")});
    fireEvent.change(input,{target:{value:"  Synthetic unsent draft\n  "}});
    await user.click(screen.getByRole("button",{name:tr("workingSummarySave")}));
    if(stage==="check"){
      await screen.findByText(tr("workingSummaryUnknown"));
      fireEvent.change(input,{target:{value:"  Synthetic newer unsent draft\n  "}});
      await user.click(screen.getByRole("button",{name:tr("workingSummaryCheck")}));
    }
    // Assert user-visible copy independently of its translation key: preserve
    // first, reopen the trusted local page, then check the saved outcome.
    const expected=locale==="en"
      ? "This request was rejected; any earlier save remains unconfirmed. First keep or manually copy your unsent draft. Then reopen the trusted local Hub page, select the same source and report, and check saved state before deciding the next step. No save will be resubmitted automatically."
      : "這次請求遭拒，先前是否已保存仍未確認。請先保留或手動複製尚未送出的草稿，再重新開啟可信的本機 Hub 頁面，選取同一來源與報告，核對保存結果後才決定下一步。系統不會自動重送保存。";
    await waitFor(()=>expect(screen.getByRole("alert")).toHaveTextContent(expected));
    expect(input).toHaveValue(stage==="save"?"  Synthetic unsent draft\n  ":"  Synthetic newer unsent draft\n  ");
    expect(input).toBeEnabled();
    expect(screen.getByRole("button",{name:tr("workingSummarySave")})).toBeDisabled();
    expect(screen.queryByText(tr("workingSummarySaved"))).not.toBeInTheDocument();
    expect(f.onSaved).not.toHaveBeenCalled();
    await act(async()=>{await Promise.resolve();await Promise.resolve();});
    expect(fetch.mock.calls.map(call=>call[1]?.method)).toEqual(stage==="save"?["GET","POST"]:["GET","POST","GET"]);
    expect(JSON.stringify(f.record)).toBe(before);
    expect(document.body.textContent).not.toMatch(/Untrusted request|Untrusted origin|CSRF/);
  });

  it("gives the same safe recovery guidance when the initial selected-context read is forbidden",async()=>{
    const f=fixture(),tr=translator(locale);
    const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValue(response({ok:false,code:"forbidden",error:"Untrusted origin"},403));
    render(<WorkingSummaryEditor {...props(f)} t={tr}/>);
    await userEvent.click(screen.getByRole("button",{name:`${tr("workingSummaryReview")} report-one`}));
    await waitFor(()=>expect(screen.getByRole("alert")).toHaveTextContent(locale==="en"?"First keep or manually copy your unsent draft":"請先保留或手動複製尚未送出的草稿"));
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button",{name:tr("workingSummarySave")})).toBeDisabled();
    expect(fetch.mock.calls.map(call=>call[1]?.method)).toEqual(["GET"]);
    expect(f.onSaved).not.toHaveBeenCalled();
  });
});

it.each([{status:403,code:"human_required"},{status:400,code:"forbidden"},{status:503,code:"forbidden"}])("does not misclassify HTTP $status / $code as forbidden-page recovery",async({status,code})=>{
  const f=fixture(),user=userEvent.setup();
  vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context}))
    .mockResolvedValueOnce(response({ok:false,code,error:"Synthetic unrelated failure"},status));
  render(<WorkingSummaryEditor {...props(f)}/>);await user.click(review());
  await screen.findByRole("textbox",{name:t("workingSummaryText")});
  await user.click(screen.getByRole("button",{name:t("workingSummarySave")}));
  expect(await screen.findByRole("alert")).toHaveTextContent(t("workingSummaryUnknown"));
  expect(f.onSaved).not.toHaveBeenCalled();
});

it("fences a late read when project/source selection changes",async()=>{
  const f=fixture(),user=userEvent.setup();let finish!:(r:Response)=>void;
  vi.spyOn(globalThis,"fetch").mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
  const {rerender}=render(<WorkingSummaryEditor {...props(f)}/>);await user.click(review());
  const other={...f.record,id:"source-other",data:{...f.record.data,id:"other",source_records:[]}};
  rerender(<WorkingSummaryEditor {...props(f)} record={other} scope={{...f.scope,projectId:"project-other"}}/>);
  await act(async()=>finish(response({ok:true,context:f.context})));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();expect(screen.queryByDisplayValue(f.context.draft_text)).not.toBeInTheDocument();expect(f.onSaved).not.toHaveBeenCalled();
});

it("fences a late POST and never refreshes a newly selected source",async()=>{
  const f=fixture(),user=userEvent.setup();let finish!:(r:Response)=>void;
  vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context})).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
  const {rerender}=render(<WorkingSummaryEditor {...props(f)}/>);await user.click(review());const input=await screen.findByRole("textbox",{name:t("workingSummaryText")});
  await user.clear(input);await user.type(input,f.saved.text);await user.click(screen.getByRole("button",{name:t("workingSummarySave")}));
  rerender(<WorkingSummaryEditor {...props(f)} scope={{...f.scope,active:false}}/>);
  await act(async()=>finish(response({ok:true,record:{...f.record,data:{...f.record.data,working_summary:f.saved}},reused:false})));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();expect(f.onSaved).not.toHaveBeenCalled();
});

it.each(["source","artifact","hash","revision"])("rejects a mismatched %s context without exposing text or saving",async field=>{
  const f=fixture(), context={...f.context};
  if(field==="source")context.source_record_id="other";
  if(field==="artifact")context.artifact_id="other";
  if(field==="hash")context.artifact_sha256="b".repeat(64);
  if(field==="revision")context.revision="invalid";
  const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValue(response({ok:true,context}));
  render(<WorkingSummaryEditor {...props(f)}/>);await userEvent.click(review());await screen.findByText(t("workingSummaryLoadFailed"));
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();expect(screen.getByRole("button",{name:t("workingSummarySave")})).toBeDisabled();expect(fetch).toHaveBeenCalledTimes(1);
});

it("requires previous revision identity when checking an unknown outcome before explicit retry",async()=>{
  const f=fixture(),user=userEvent.setup();
  const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context})).mockRejectedValueOnce(new TypeError("offline"))
    .mockResolvedValueOnce(response({ok:true,context:{...f.context,revision:"2".repeat(64),working_summary:{...f.saved,previous_revision:"3".repeat(64)}}}))
    .mockResolvedValueOnce(response({ok:true,record:{...f.record,data:{...f.record.data,working_summary:{...f.saved,previous_revision:"2".repeat(64)}}},reused:false}));
  render(<WorkingSummaryEditor {...props(f)}/>);await user.click(review());const input=await screen.findByRole("textbox",{name:t("workingSummaryText")});
  await user.clear(input);await user.type(input,f.saved.text);await user.click(screen.getByRole("button",{name:t("workingSummarySave")}));await screen.findByText(t("workingSummaryUnknown"));
  await user.click(screen.getByRole("button",{name:t("workingSummaryCheck")}));await screen.findByText(t("workingSummaryChecked"));
  expect(f.onSaved).not.toHaveBeenCalled();expect(input).toHaveValue(f.saved.text);
  await user.click(screen.getByRole("button",{name:t("workingSummarySave")}));await screen.findByText(t("workingSummarySaved"));
  expect(fetch.mock.calls.map(c=>c[1]?.method)).toEqual(["GET","POST","GET","POST"]);
  expect(JSON.parse(String(fetch.mock.calls[3][1]?.body)).expected_revision).toBe("2".repeat(64));
});

it("sends normalized prose and recognizes its saved result while keeping unsaved textarea bytes",async()=>{
  const f=fixture(),user=userEvent.setup();
  const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response({ok:true,context:f.context})).mockResolvedValueOnce(response({ok:true,record:{...f.record,data:{...f.record.data,working_summary:f.saved}},reused:false}));
  render(<WorkingSummaryEditor {...props(f)}/>);await user.click(review());const input=await screen.findByRole("textbox",{name:t("workingSummaryText")});
  fireEvent.change(input,{target:{value:`  ${f.saved.text}\n  `}});
  expect(input).toHaveValue(`  ${f.saved.text}\n  `);await user.click(screen.getByRole("button",{name:t("workingSummarySave")}));
  await screen.findByText(t("workingSummarySaved"));expect(JSON.parse(String(fetch.mock.calls[1][1]?.body)).text).toBe(f.saved.text);
});

it("prevents oversized saves using Unicode codepoints without sending a POST",async()=>{
  const f=fixture(),user=userEvent.setup();const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValue(response({ok:true,context:f.context}));
  render(<WorkingSummaryEditor {...props(f)}/>);await user.click(review());const input=await screen.findByRole("textbox",{name:t("workingSummaryText")});
  fireEvent.change(input,{target:{value:"🌿".repeat(40000)}});expect(screen.getByRole("button",{name:t("workingSummarySave")})).toBeEnabled();
  fireEvent.change(input,{target:{value:"🌿".repeat(40001)}});expect(screen.getByText(t("workingSummaryTooLong"))).toBeVisible();
  expect(screen.getByRole("button",{name:t("workingSummarySave")})).toBeDisabled();expect(fetch).toHaveBeenCalledTimes(1);
});

it("clears a selected artifact on hash change and ignores its late context",async()=>{
  const f=fixture(),user=userEvent.setup();let finish!:(r:Response)=>void;
  const updatedArtifact={...f.artifact,sha256:"b".repeat(64)};
  const fetch=vi.spyOn(globalThis,"fetch").mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}))
    .mockResolvedValueOnce(response({ok:true,context:{...f.context,artifact_sha256:updatedArtifact.sha256,draft_text:"New exact report draft"}}));
  const {rerender}=render(<WorkingSummaryEditor {...props(f)}/>);await user.click(review());
  const updatedRecord={...f.record,data:{...f.record.data,source_records:(f.record.data.source_records as Record<string,unknown>[]).map(row=>({...row,text_sha256:updatedArtifact.sha256}))}};
  rerender(<WorkingSummaryEditor {...props(f)} record={updatedRecord} scope={{...f.scope,artifacts:[updatedArtifact]}}/>);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();await user.click(review());expect(await screen.findByRole("textbox",{name:t("workingSummaryText")})).toHaveValue("New exact report draft");
  await act(async()=>finish(response({ok:true,context:f.context})));expect(screen.getByRole("textbox",{name:t("workingSummaryText")})).toHaveValue("New exact report draft");expect(fetch).toHaveBeenCalledTimes(2);
});

describe.each(["en","zh-TW"] as const)("uncertain save with newer local edits %s",locale=>{
  it.each(["before","during"])("retains newer local edits made %s the saved-state GET until an explicit save",async timing=>{
    const f=fixture(),tr=translator(locale),user=userEvent.setup();
    const newerDraft="  My newer unsaved summary\n  ";
    const freshRevision="2".repeat(64);
    let committed:Record<string,unknown>|null=null;
    let finishCheck!:(r:Response)=>void;
    const fetch=vi.spyOn(globalThis,"fetch")
      .mockResolvedValueOnce(response({ok:true,context:f.context}))
      .mockImplementationOnce(async()=>{committed=f.saved;throw new TypeError("response lost after commit");})
      .mockImplementationOnce(()=>new Promise(resolve=>{finishCheck=resolve;}))
      .mockImplementationOnce(async()=>{
        committed={...f.saved,text:newerDraft.trim(),previous_revision:freshRevision};
        return response({ok:true,record:{...f.record,data:{...f.record.data,working_summary:committed}},reused:false});
      });
    render(<WorkingSummaryEditor {...props(f)} t={tr}/>);
    await user.click(screen.getByRole("button",{name:`${tr("workingSummaryReview")} report-one`}));
    const input=await screen.findByRole("textbox",{name:tr("workingSummaryText")});
    fireEvent.change(input,{target:{value:f.saved.text}});
    await user.click(screen.getByRole("button",{name:tr("workingSummarySave")}));
    await screen.findByText(tr("workingSummaryUnknown"));expect(committed).toEqual(f.saved);
    if(timing==="before")fireEvent.change(input,{target:{value:newerDraft}});
    await user.click(screen.getByRole("button",{name:tr("workingSummaryCheck")}));
    if(timing==="during")fireEvent.change(input,{target:{value:newerDraft}});
    await act(async()=>finishCheck(response({ok:true,context:{...f.context,revision:freshRevision,working_summary:committed}})));
    expect(f.onSaved).not.toHaveBeenCalled();
    expect(screen.queryByText(tr("workingSummarySaved"))).not.toBeInTheDocument();
    expect(screen.getByText(tr("workingSummaryEarlierSaved"))).toBeVisible();
    expect(input).toHaveValue(newerDraft);expect(input).toBeEnabled();
    expect(screen.getByRole("button",{name:tr("workingSummarySave")})).toBeEnabled();
    expect(fetch.mock.calls.map(call=>call[1]?.method)).toEqual(["GET","POST","GET"]);
    await user.click(screen.getByRole("button",{name:tr("workingSummarySave")}));
    await screen.findByText(tr("workingSummarySaved"));expect(f.onSaved).toHaveBeenCalledOnce();
    expect(JSON.parse(String(fetch.mock.calls[3][1]?.body))).toMatchObject({text:newerDraft.trim(),expected_revision:freshRevision});
    expect(fetch.mock.calls.map(call=>call[1]?.method)).toEqual(["GET","POST","GET","POST"]);
  });
});

describe.each(["en","zh-TW"] as const)("committed HTTP 503 recovery %s",locale=>{
  it.each(["pointer","keyboard"])("checks saved B through %s activation, retaining newer B2 for explicit save",async activation=>{
    const f=fixture(),tr=translator(locale),user=userEvent.setup();
    const original=JSON.stringify(f.record),freshRevision="2".repeat(64);
    const initial={...f.context,working_summary:{...f.saved,text:"QA working A",previous_revision:"0".repeat(64)}};
    const committedB={...f.saved,text:"QA working B"};
    const savedB2={...f.saved,text:"QA working B2",previous_revision:freshRevision};
    const fetch=vi.spyOn(globalThis,"fetch")
      .mockResolvedValueOnce(response({ok:true,context:initial}))
      .mockResolvedValueOnce(response({ok:false,code:"synthetic_response_loss",error:"Synthetic response unavailable; check saved state"},503))
      .mockResolvedValueOnce(response({ok:true,context:{...f.context,revision:freshRevision,working_summary:committedB}}))
      .mockResolvedValueOnce(response({ok:true,record:{...f.record,data:{...f.record.data,working_summary:savedB2}},reused:false}));
    render(<WorkingSummaryEditor {...props(f)} t={tr}/>);
    await user.click(screen.getByRole("button",{name:`${tr("workingSummaryReview")} report-one`}));
    const input=await screen.findByRole("textbox",{name:tr("workingSummaryText")});
    expect(input).toHaveValue("QA working A");
    fireEvent.change(input,{target:{value:committedB.text}});
    await user.click(screen.getByRole("button",{name:tr("workingSummarySave")}));
    await screen.findByText(tr("workingSummaryUnknown"));
    fireEvent.change(input,{target:{value:savedB2.text}});
    const check=screen.getByRole("button",{name:tr("workingSummaryCheck")});
    expect(check).toBeEnabled();
    if(activation==="keyboard") {check.focus();await user.keyboard("{Enter}");}
    else await user.click(check);
    await screen.findByText(tr("workingSummaryEarlierSaved"));
    expect(input).toHaveValue(savedB2.text);
    expect(input).toBeEnabled();
    expect(screen.getByRole("button",{name:tr("workingSummarySave")})).toBeEnabled();
    expect(f.onSaved).not.toHaveBeenCalled();
    expect(fetch.mock.calls.map(call=>call[1]?.method)).toEqual(["GET","POST","GET"]);
    await user.click(screen.getByRole("button",{name:tr("workingSummarySave")}));
    await screen.findByText(tr("workingSummarySaved"));
    expect(JSON.parse(String(fetch.mock.calls[3][1]?.body))).toEqual({
      source_record_id:f.record.id,artifact_id:f.artifact.id,artifact_sha256:sha,
      expected_revision:freshRevision,text:savedB2.text,
    });
    expect(fetch.mock.calls.map(call=>call[1]?.method)).toEqual(["GET","POST","GET","POST"]);
    expect(f.onSaved).toHaveBeenCalledOnce();
    expect(JSON.stringify(f.record)).toBe(original);
  });
});
