import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LiteratureLibrary } from "./LiteratureLibrary";
import { NativeSummaryReader } from "./NativeSummaryReader";
import { translator } from "./i18n";
import type { ObservationReadScope } from "./ObservationPreview";
import type { ResearchRecord } from "./types";
const t = translator("en");
function fixture(id = "one") {
  const record: ResearchRecord & {native_summary_available?: boolean} = {native_summary_available:true,id, kind:"source", data:{title:`Synthetic ${id}`, locator:`https://example.invalid/${id}`}};
  const artifact = {id:`artifact-${id}`,project_id:"project",source_record_id:id,role:"evidence",sha256:"a".repeat(64),current:true};
  const scope: ObservationReadScope = {projectId:"project",artifacts:[artifact],active:true,revision:0};
  const quote = "Synthetic 🧪 evidence.";
  const end = 4 + Array.from(quote).length;
  const claim = {text:`Synthetic ${id} claim <img src=x onerror=alert(1)>`,status:"supported",reason:"Synthetic evidence fixture only.",evidence:[{artifact_id:artifact.id,quote,start:4,end}]};
  const native_summary = {human_acceptance:"pending",semantic_support:"not_assessed",saved_at:"2026-11-11T00:00:00Z",schema:"native-source-summary-v1",project_id:"project",source_record_id:id,source:{title:record.data.title,locator:record.data.locator},source_revision:"b".repeat(64),expected_revision:"d".repeat(64),reading_scope:"unknown",
    selections:[{artifact_id:artifact.id,sha256:artifact.sha256,start:4,end,text_sha256:"c".repeat(64)}],
    sections:{why:[claim],objective:[{...claim,status:"analyst_inference"}],methods:[{text:"Unknown in synthetic fixture.",status:"unknown",reason:"Not supplied in synthetic selection.",evidence:[]}],findings:[claim],conclusions:[claim],key_points:[claim],limitations:[claim]}};
  return {record,scope,artifact,body:{ok:true,status:"current",native_summary,human_acceptance:"pending",semantic_support:"not_assessed"}};
}
const response = (v:unknown) => new Response(JSON.stringify(v), {headers:{"Content-Type":"application/json"}});
describe("native summary selected-source reader", () => {
  it("does not probe sources without a registered native candidate", () => {
    const f=fixture(); delete f.record.native_summary_available;
    const fetch=vi.spyOn(globalThis,"fetch");
    render(<NativeSummaryReader record={f.record} scope={f.scope} t={t}/>);
    expect(screen.getByText(t("nativeMissing"))).toBeVisible();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("reuses the selected library reading view and preserves existing saved prose", async () => {
    const f=fixture(); f.record.data.summary="Synthetic saved abstract remains unchanged.";
    vi.spyOn(globalThis,"fetch").mockResolvedValue(response(f.body));
    render(<LiteratureLibrary sources={[f.record]} screenings={[]} t={t} onScreen={async()=>{}} onPrepare={()=>{}} observationRead={f.scope}/>);
    expect(await screen.findByText(t("nativeScope"))).toBeVisible();
    expect(screen.getByText("Synthetic saved abstract remains unchanged.")).toBeVisible();
    expect(screen.getByRole("region",{name:t("nativeTitle")})).toBeVisible();
  });
  it.each(["en", "zh-TW"] as const)("classifies native-only presence consistently in %s without eagerly reading other rows", async locale => {
    const translate=translator(locale), f=fixture(), other=fixture("two"), missing=fixture("missing");
    delete missing.record.native_summary_available;
    const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValue(response(f.body));
    render(<LiteratureLibrary sources={[f.record,other.record,missing.record]} screenings={[]} t={translate} onScreen={async()=>{}} onPrepare={()=>{}} observationRead={f.scope}/>);
    await screen.findByText(translate("nativeScope"));
    expect(screen.getByRole("button",{name:`${translate("catalogNeedsSummary")} (1)`})).toBeVisible();
    const row=screen.getByRole("row",{name:/Synthetic one/});
    expect(within(row).getByText(translate("catalogNativeRegistered"))).toBeVisible();
    expect(within(row).queryByText(translate("catalogNeedsSummary"))).not.toBeInTheDocument();
    const detail=screen.getByRole("complementary",{name:translate("catalogDetail")});
    expect(within(detail).getByText(translate("catalogNoSeparateSummary"))).toBeVisible();
    expect(within(detail).queryByText(translate("catalogNoSummary"))).not.toBeInTheDocument();
    expect(within(screen.getByRole("region",{name:translate("catalogOrganizationState")})).queryByText(translate("catalogNeedsSummary"))).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button",{name:`${translate("catalogNeedsSummary")} (1)`}));
    expect(screen.queryByRole("button",{name:"Synthetic one"})).not.toBeInTheDocument();
    expect(screen.getByRole("button",{name:"Synthetic missing"})).toBeVisible();
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it.each(["loading","stale","unavailable","missing"])("keeps registered presence distinct from %s reader status", async status => {
    const f=fixture();
    const fetch=vi.spyOn(globalThis,"fetch");
    if(status==="loading") fetch.mockImplementation(()=>new Promise(()=>{}));
    else fetch.mockResolvedValue(response({...f.body,status}));
    render(<LiteratureLibrary sources={[f.record]} screenings={[]} t={t} onScreen={async()=>{}} onPrepare={()=>{}} observationRead={f.scope}/>);
    expect(screen.getByRole("button",{name:`${t("catalogNeedsSummary")} (0)`})).toBeVisible();
    expect(screen.getAllByText(t("catalogNativeRegistered"))).toHaveLength(2);
    expect(screen.getByText(t("catalogNoSeparateSummary"))).toBeVisible();
    if(status!=="loading") await screen.findByText(t(status==="stale"?"nativeStale":status==="missing"?"nativeMissing":"nativeUnavailable"));
    expect(screen.queryByText(t("nativeScope"))).not.toBeInTheDocument();
    expect(screen.queryByText(/Synthetic one claim/)).not.toBeInTheDocument();
    expect(screen.getByText(t("nativePending"))).toBeVisible();
  });
  it.each([undefined,false,"true",1,{},null])("does not treat malformed/absent presence %s as registered", flag => {
    const f=fixture(); Object.assign(f.record,{native_summary_available:flag});
    const fetch=vi.spyOn(globalThis,"fetch");
    render(<LiteratureLibrary sources={[f.record]} screenings={[]} t={t} onScreen={async()=>{}} onPrepare={()=>{}} observationRead={f.scope}/>);
    expect(screen.getByRole("button",{name:`${t("catalogNeedsSummary")} (1)`})).toBeVisible();
    expect(screen.getByText(t("catalogNoSummary"))).toBeVisible();
    expect(screen.queryByText(t("catalogNativeRegistered"))).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("does not apply Workspace candidate presence to library notes", () => {
    const f=fixture(); f.record.kind="library-note";
    const fetch=vi.spyOn(globalThis,"fetch");
    render(<LiteratureLibrary sources={[f.record]} screenings={[]} t={t} onScreen={async()=>{}} onPrepare={()=>{}} observationRead={f.scope}/>);
    expect(screen.getByRole("button",{name:`${t("catalogNeedsSummary")} (1)`})).toBeVisible();
    expect(screen.getByText(t("catalogNoSummary"))).toBeVisible();
    expect(screen.queryByText(t("catalogNativeRegistered"))).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("allows explicitly labelled inference without evidence and preserves its reason", async () => {
    const f=fixture(); f.body.native_summary.sections.objective[0].evidence=[];
    vi.spyOn(globalThis,"fetch").mockResolvedValue(response(f.body));
    render(<NativeSummaryReader record={f.record} scope={f.scope} t={t}/>);
    expect(await screen.findByText(t("nativeScope"))).toBeVisible();
    expect(screen.getByText("analyst_inference")).toBeVisible();
    expect(screen.getByText(/Declared reading scope: unknown/)).toBeVisible();
  });
  it("renders all seven sections, epistemic labels, reasons, exact Unicode evidence and hashes safely with GET only", async () => {
    const f=fixture(); const before=JSON.stringify(f.record);
    const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValue(response(f.body));
    const {container}=render(<NativeSummaryReader record={f.record} scope={f.scope} t={t}/>);
    expect(await screen.findByText(t("nativeScope"))).toBeVisible();
    for (const title of ["nativeWhy","nativeObjective","nativeMethods","nativeFindings","nativeConclusions","nativeKeyPoints","nativeLimitations"] as const) expect(screen.getByText(t(title))).toBeVisible();
    expect(screen.getAllByText("supported").length).toBeGreaterThan(0);
    expect(screen.getByText("analyst_inference")).toBeVisible();
    expect(screen.getByText("unknown")).toBeVisible();
    expect(screen.getByText(t("nativePending"))).toBeVisible();
    expect(screen.getAllByText("Synthetic 🧪 evidence.").length).toBeGreaterThan(0);
    expect(screen.getAllByText("a".repeat(64)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/\[4, 25\)/).length).toBeGreaterThan(0);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/projects/project/native-summary?source_record_id=one");
    expect(fetch.mock.calls[0][1]?.method).toBe("GET");
    expect(JSON.stringify(f.record)).toBe(before);
  });
  it.each(["missing","stale","unavailable"])("hides even supplied prose when server reports %s", async status => {
    const f=fixture(); vi.spyOn(globalThis,"fetch").mockResolvedValue(response({...f.body,status}));
    render(<NativeSummaryReader record={f.record} scope={f.scope} t={t}/>);
    expect(await screen.findByText(t(status === "missing" ? "nativeMissing" : status === "stale" ? "nativeStale" : "nativeUnavailable"))).toBeVisible();
    expect(screen.queryByText(t("nativeScope"))).not.toBeInTheDocument();
  });
  it.each(["source","project","title","locator","hash","current","offset","section","evidence","status"])("rejects malformed or mismatched %s", async kind => {
    const f=fixture(); const s=f.body.native_summary;
    if(kind==="source") s.source_record_id="other";
    if(kind==="project") s.project_id="other";
    if(kind==="title") s.source.title="other";
    if(kind==="locator") s.source.locator="https://example.invalid/other";
    if(kind==="hash") s.selections[0].sha256="d".repeat(64);
    if(kind==="current") f.artifact.current=false;
    if(kind==="offset") s.sections.why[0].evidence[0].end++;
    if(kind==="section") s.sections.methods=[];
    if(kind==="evidence") s.sections.why[0].evidence=[];
    if(kind==="status") s.sections.why[0].status="accepted";
    vi.spyOn(globalThis,"fetch").mockResolvedValue(response(f.body));
    render(<NativeSummaryReader record={f.record} scope={f.scope} t={t}/>);
    expect(await screen.findByText(t("nativeStale"))).toBeVisible();
    expect(screen.queryByText(t("nativeScope"))).not.toBeInTheDocument();
  });
  it.each(["human_acceptance","semantic_support","saved_at"])("hides prose with missing persisted %s", async marker => {
    const f=fixture(); delete (f.body.native_summary as Record<string, unknown>)[marker];
    vi.spyOn(globalThis,"fetch").mockResolvedValue(response(f.body));
    render(<NativeSummaryReader record={f.record} scope={f.scope} t={t}/>);
    expect(await screen.findByText(t("nativeStale"))).toBeVisible();
    expect(screen.queryByText(t("nativeScope"))).not.toBeInTheDocument();
  });
  it("cancels rapid switching and ignores out-of-order responses, including a return to the first source", async () => {
    const a=fixture(), b=fixture("two"); let late!: (r:Response)=>void;
    const fetch=vi.spyOn(globalThis,"fetch").mockImplementationOnce(()=>new Promise(resolve=>{late=resolve;})).mockResolvedValueOnce(response(b.body)).mockResolvedValueOnce(response({...a.body,status:"missing"}));
    const {rerender}=render(<NativeSummaryReader record={a.record} scope={a.scope} t={t}/>);
    await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(1));
    rerender(<NativeSummaryReader record={b.record} scope={b.scope} t={t}/>);
    expect((await screen.findAllByText(/Synthetic two claim/)).length).toBeGreaterThan(0);
    rerender(<NativeSummaryReader record={a.record} scope={a.scope} t={t}/>);
    expect(screen.queryByText(/Synthetic two claim/)).not.toBeInTheDocument();
    expect(await screen.findByText(t("nativeMissing"))).toBeVisible();
    await act(async()=>late(response(a.body)));
    expect(screen.queryByText(/Synthetic one claim/)).not.toBeInTheDocument();
    expect(fetch.mock.calls[0][1]?.signal?.aborted).toBe(true);
  });
  it("hides stale prose immediately on refresh, retries once and does not refetch on unrelated rerenders", async () => {
    const f=fixture(); const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(response(f.body)).mockResolvedValue(response({...f.body,status:"stale"}));
    const {rerender}=render(<NativeSummaryReader record={f.record} scope={f.scope} t={t}/>);
    await screen.findByText(t("nativeScope"));
    rerender(<NativeSummaryReader record={{...f.record}} scope={{...f.scope}} t={t}/>);
    expect(fetch).toHaveBeenCalledTimes(1);
    rerender(<NativeSummaryReader record={f.record} scope={{...f.scope,revision:1}} t={t}/>);
    expect(screen.queryByText(t("nativeScope"))).not.toBeInTheDocument();
    expect(await screen.findByText(t("nativeStale"))).toBeVisible();
    expect(fetch).toHaveBeenCalledTimes(2);
  });
  it("does not read inactive or library-note records and cancels on unmount", async () => {
    const f=fixture(); const fetch=vi.spyOn(globalThis,"fetch").mockImplementation(()=>new Promise(()=>{}));
    const {rerender,unmount}=render(<NativeSummaryReader record={f.record} scope={{...f.scope,active:false}} t={t}/>);
    rerender(<NativeSummaryReader record={{...f.record,kind:"library-note"}} scope={f.scope} t={t}/>);
    expect(fetch).not.toHaveBeenCalled();
    rerender(<NativeSummaryReader record={f.record} scope={f.scope} t={t}/>);
    await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(1));
    unmount(); expect(fetch.mock.calls[0][1]?.signal?.aborted).toBe(true);
  });
  it.each([null,{}, {ok:true,status:"current",native_summary:null}, {ok:true,status:"accepted"}])("treats empty/malformed envelopes as unknown", async body => {
    const f=fixture(); vi.spyOn(globalThis,"fetch").mockResolvedValue(response(body));
    render(<NativeSummaryReader record={f.record} scope={f.scope} t={t}/>);
    expect(await screen.findByText(t("nativeUnavailable"))).toBeVisible();
  });
  it("localizes stale state and does not disclose server errors", async () => {
    const f=fixture(); const zh=translator("zh-TW");
    vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(JSON.stringify({ok:false,error:"/private/location",code:"stale_input"}),{status:409}));
    render(<NativeSummaryReader record={f.record} scope={f.scope} t={zh}/>);
    expect(await screen.findByText(zh("nativeStale"))).toBeVisible();
    expect(screen.queryByText(/private/)).not.toBeInTheDocument();
  });
});
