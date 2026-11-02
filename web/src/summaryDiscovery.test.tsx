import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LiteratureLibrary } from "./LiteratureLibrary";
import { translator } from "./i18n";
import type { ResearchRecord } from "./types";

function fixture() {
  const record: ResearchRecord = {id:"hub-one", kind:"source", data:{id:"one", title:"Synthetic draft paper", reading_level:"abstract-snippet", human_acceptance:"pending", source_records:[{
    observation_id:"generated-one", source_id:"one", work_id:"work-one", status:"available", evidence_level:"generated-summary", text_path:"report.md", text_sha256:"a".repeat(64),
  }]}};
  const artifact={id:"report-one", project_id:"project", source_record_id:record.id, path:"report.md", role:"evidence", sha256:"a".repeat(64), current:true};
  const text="# Generated summary observation: one\n\nEvidence level: generated-summary. This is report-derived prose, NOT an original abstract or publisher capture.\n\n## Supplied generated summary\nSynthetic generated prose.\n\nRole candidate (not human acceptance): Method candidate\nReported later reading: abstract\nReported observation time: 2026-11-01T01:20:49Z\nReported sources: [\"https://example.invalid/source\"]\n";
  const preview={artifact_id:artifact.id,path:artifact.path,sha256:artifact.sha256,text,bytes_read:new TextEncoder().encode(text).length,codepoint_length:Array.from(text).length,truncated:false};
  return {record,artifact,preview,scope:{projectId:"project",artifacts:[artifact],active:true,revision:0}};
}
const response=(preview:unknown)=>new Response(JSON.stringify({ok:true,preview}),{status:200,headers:{"Content-Type":"application/json"}});

describe.each(["en","zh-TW"] as const)("generated draft discovery %s",locale=>{
  const t=translator(locale);
  it("marks registration without eager row reads, opens generated history by keyboard and returns to the same title",async()=>{
    const f=fixture(), user=userEvent.setup(), before=JSON.stringify(f.record);
    const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValue(response(f.preview));
    render(<LiteratureLibrary sources={[f.record]} screenings={[]} t={t} onScreen={vi.fn()} onPrepare={vi.fn()} observationRead={f.scope}/>);
    const row=within(screen.getByRole("table")).getByRole("button",{name:f.record.data.title as string});
    expect(row).toHaveAccessibleDescription(t("catalogDraftRegistered"));
    expect(screen.getByRole("button",{name:`${t("catalogNeedsSummary")} (1)`})).toBeVisible();
    expect(await screen.findByText("Synthetic generated prose.")).not.toBeVisible();
    const open=screen.getByRole("button",{name:t("catalogOpenDrafts")});
    open.focus();await user.keyboard("{Enter}");
    const history=screen.getByRole("region",{name:t("observationHistory")});
    const summary=within(history).getByText(`${t("observationGenerated")} · generated-one`);
    expect(summary).toHaveFocus();expect(screen.getByText("Synthetic generated prose.")).toBeVisible();
    expect(screen.getByText(t("observationVersionPending"))).toBeVisible();
    expect(screen.getByText(t("observationReportedReading"))).not.toBeVisible();
    await user.click(screen.getByRole("button",{name:t("catalogBackToList")}));
    expect(row).toHaveFocus();expect(fetch).toHaveBeenCalledTimes(1);
    expect(JSON.stringify(f.record)).toBe(before);
  });

  it("keeps saved human prose primary while registering a separate generated draft",async()=>{
    const f=fixture();f.record.data.summary="Preserved human wording.";
    vi.spyOn(globalThis,"fetch").mockResolvedValue(response(f.preview));
    render(<LiteratureLibrary sources={[f.record]} screenings={[]} t={t} onScreen={vi.fn()} onPrepare={vi.fn()} observationRead={f.scope}/>);
    expect(screen.getByText("Preserved human wording.")).toBeVisible();
    expect(screen.getByRole("button",{name:`${t("catalogNeedsSummary")} (0)`})).toBeVisible();
    await userEvent.click(screen.getByRole("button",{name:t("catalogOpenDrafts")}));
    expect(await screen.findByText("Synthetic generated prose.")).toBeVisible();
    expect(screen.getByText("Preserved human wording.")).toBeVisible();
  });

  it("announces loading, hides failed text and recovers only on explicit refresh without changing scope",async()=>{
    const f=fixture();let complete!:(r:Response)=>void;
    const fetch=vi.spyOn(globalThis,"fetch").mockImplementationOnce(()=>new Promise(resolve=>{complete=resolve;})).mockResolvedValueOnce(response(f.preview));
    const props={sources:[f.record],screenings:[],t,onScreen:vi.fn(),onPrepare:vi.fn()};
    const {rerender}=render(<LiteratureLibrary {...props} observationRead={f.scope}/>);
    expect(screen.getByText(t("observationPreviewLoading"))).toBeVisible();
    await userEvent.click(screen.getByRole("button",{name:t("catalogOpenDrafts")}));
    await act(async()=>complete(new Response(JSON.stringify({ok:false,error:"private synthetic path",code:"source_unavailable"}),{status:503})));
    expect(await screen.findByText(t("observationPreviewError"))).toBeVisible();
    expect(screen.queryByText("private synthetic path")).not.toBeInTheDocument();
    expect(screen.queryByText("Synthetic generated prose.")).not.toBeInTheDocument();
    rerender(<LiteratureLibrary {...props} observationRead={{...f.scope}}/>);expect(fetch).toHaveBeenCalledTimes(1);
    rerender(<LiteratureLibrary {...props} observationRead={{...f.scope,revision:1}}/>);
    expect(await screen.findByText("Synthetic generated prose.")).toBeVisible();expect(fetch).toHaveBeenCalledTimes(2);
    expect(f.record.data.reading_level).toBe("abstract-snippet");expect(f.record.data.human_acceptance).toBe("pending");
  });
});

it.each(["empty-body","malformed-report"])("shows an unknown body for a registered %s without claiming availability",async kind=>{
  const f=fixture(),t=translator("en");
  f.preview.text=kind==="empty-body" ? f.preview.text.replace("Synthetic generated prose.","") : "Not a generated report.";
  f.preview.bytes_read=new TextEncoder().encode(f.preview.text).length;f.preview.codepoint_length=Array.from(f.preview.text).length;
  vi.spyOn(globalThis,"fetch").mockResolvedValue(response(f.preview));
  render(<LiteratureLibrary sources={[f.record]} screenings={[]} t={t} onScreen={vi.fn()} onPrepare={vi.fn()} observationRead={f.scope}/>);
  await userEvent.click(screen.getByRole("button",{name:t("catalogOpenDrafts")}));
  expect(await screen.findByText(t("observationBodyUnknown"))).toBeVisible();
  expect(screen.queryByText("Synthetic generated prose.")).not.toBeInTheDocument();
  expect(screen.getByRole("button",{name:`${t("catalogNeedsSummary")} (1)`})).toBeVisible();
});

it.each(["no-reference","wrong-project","wrong-source","wrong-hash","duplicate","readonly-note"])("does not advertise a generated draft for %s",kind=>{
  const f=fixture(), t=translator("en");
  if(kind==="no-reference")f.record.data.source_records=[];
  if(kind==="wrong-project")f.artifact.project_id="elsewhere";
  if(kind==="wrong-source")f.artifact.source_record_id="someone-else";
  if(kind==="wrong-hash")f.artifact.sha256="b".repeat(64);
  if(kind==="duplicate")f.scope.artifacts.push({...f.artifact,id:"duplicate"});
  if(kind==="readonly-note")f.record.kind="library-note";
  const fetch=vi.spyOn(globalThis,"fetch");
  render(<LiteratureLibrary sources={[f.record]} screenings={[]} t={t} onScreen={vi.fn()} onPrepare={vi.fn()} observationRead={f.scope}/>);
  expect(screen.queryByRole("button",{name:t("catalogOpenDrafts")})).not.toBeInTheDocument();
  expect(within(screen.getByRole("table")).getByRole("button",{name:f.record.data.title as string})).not.toHaveAttribute("aria-describedby");
  expect(fetch).not.toHaveBeenCalled();
});
