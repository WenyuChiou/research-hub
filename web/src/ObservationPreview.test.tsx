import { act, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ObservationPreview, observationArtifacts, type ObservationReadScope } from "./ObservationPreview";
import { translator } from "./i18n";
import type { ResearchRecord } from "./types";

const t = translator("en");
function fixture(id = "one") {
  const hash = "a".repeat(64);
  const text = `# Generated summary observation: ${id}\n\nEvidence level: generated-summary. This is report-derived prose, NOT an original abstract or publisher capture.\n\n## Supplied generated summary\nSynthetic ${id} draft.\n\nRole candidate (not human acceptance): Method candidate\nReported later reading: abstract\nReported observation time: 2026-11-01T01:20:49Z\nReported sources: ["https://example.invalid/source"]\n`;
  const record: ResearchRecord = {id:`hub-${id}`,kind:"source",data:{id,title:`Synthetic ${id}`,reading_level:"abstract-snippet",source_records:[{
    observation_id:`obs-${id}`,source_id:id,work_id:`work-${id}`,status:"available",evidence_level:"generated-summary",text_path:`${id}.md`,text_sha256:hash,
  }]}};
  const artifact = {id:`artifact-${id}`,project_id:"project",source_record_id:record.id,path:`${id}.md`,role:"evidence",sha256:hash,current:true};
  const preview = {artifact_id:artifact.id,path:artifact.path,sha256:hash,text,codepoint_length:Array.from(text).length,bytes_read:new TextEncoder().encode(text).length,truncated:false};
  const scope: ObservationReadScope = {projectId:"project",artifacts:[artifact],active:true};
  return {record,scope,preview,artifact};
}
const response = (preview:unknown) => new Response(JSON.stringify({ok:true,preview}), {status:200,headers:{"Content-Type":"application/json"}});

describe("scoped observation preview reader", () => {
  it("uses the existing read API and leaves source metadata unchanged", async () => {
    const f = fixture(); const before = JSON.stringify(f.record);
    const fetch = vi.spyOn(globalThis,"fetch").mockResolvedValue(response(f.preview));
    render(<ObservationPreview record={f.record} scope={f.scope} t={t} />);
    expect(await screen.findByText("Synthetic one draft.")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/projects/project/artifacts/artifact-one/text");
    expect(fetch.mock.calls[0][1]?.method).toBe("GET");
    expect(JSON.stringify(f.record)).toBe(before);
  });
  it.each(["inactive","project","source","hash","missing-id","duplicate"])("does not read unselected or ambiguous %s references", kind => {
    const f=fixture();
    if(kind==="inactive") f.scope.active=false;
    if(kind==="project") f.artifact.project_id="other";
    if(kind==="source") f.artifact.source_record_id="other";
    if(kind==="hash") f.artifact.sha256="b".repeat(64);
    if(kind==="missing-id") delete f.record.data.id;
    if(kind==="duplicate") f.scope.artifacts.push({...f.artifact,id:"duplicate"});
    const fetch=vi.spyOn(globalThis,"fetch");
    expect(observationArtifacts(f.record,f.scope)).toEqual([]);
    render(<ObservationPreview record={f.record} scope={f.scope} t={t} />);
    expect(fetch).not.toHaveBeenCalled();
  });
  it("shows a generic unavailable status without exposing backend errors", async () => {
    const f=fixture();
    vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(JSON.stringify({ok:false,error:"private path /unrelated/secret",code:"stale_input"}),{status:409}));
    render(<ObservationPreview record={f.record} scope={f.scope} t={t} />);
    expect(await screen.findByText(t("observationPreviewError"))).toBeVisible();
    expect(screen.queryByText(/unrelated\/secret/)).not.toBeInTheDocument();
    expect(screen.queryByText("Synthetic one draft.")).not.toBeInTheDocument();
  });
  it("cancels stale reads and never shows a previous source's late body", async () => {
    const a=fixture("one"), b=fixture("two");
    let late!: (value:Response)=>void;
    const fetch=vi.spyOn(globalThis,"fetch").mockImplementationOnce(()=>new Promise(resolve=>{late=resolve;})).mockResolvedValueOnce(response(b.preview));
    const {rerender}=render(<ObservationPreview record={a.record} scope={a.scope} t={t} />);
    await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(1));
    rerender(<ObservationPreview record={b.record} scope={b.scope} t={t} />);
    expect(await screen.findByText("Synthetic two draft.")).toBeInTheDocument();
    await act(async()=>late(response(a.preview)));
    expect(screen.queryByText("Synthetic one draft.")).not.toBeInTheDocument();
    expect(fetch.mock.calls[0][1]?.signal?.aborted).toBe(true);
  });
  it("keeps a successful preview when another observation is unavailable", async () => {
    const a=fixture("one"), extra=fixture("one");
    const second={...extra.artifact,id:"second",path:"second.md"};
    a.scope.artifacts.push(second);
    (a.record.data.source_records as unknown[]).push({...((a.record.data.source_records as object[])[0]),observation_id:"second",text_path:"second.md"});
    vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response(a.preview)).mockRejectedValueOnce(new Error("Unavailable"));
    render(<ObservationPreview record={a.record} scope={a.scope} t={t} />);
    expect(await screen.findByText(t("observationPreviewError"))).toBeVisible();
    expect(screen.getByText("Synthetic one draft.")).toBeInTheDocument();
  });
  it("invalidates an already displayed body when Refresh reports current=false on the same artifact", async () => {
    const f=fixture();
    const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response(f.preview)).mockResolvedValueOnce(new Response(JSON.stringify({ok:false,error:"Changed file",code:"stale_input"}),{status:409}));
    const {rerender}=render(<ObservationPreview record={f.record} scope={f.scope} t={t} />);
    expect(await screen.findByText("Synthetic one draft.")).toBeInTheDocument();
    rerender(<ObservationPreview record={f.record} scope={{...f.scope,artifacts:[{...f.artifact,current:false}]}} t={t} />);
    expect(screen.queryByText("Synthetic one draft.")).not.toBeInTheDocument();
    expect(await screen.findByText(t("observationPreviewError"))).toBeVisible();
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
