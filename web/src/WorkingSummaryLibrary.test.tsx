import { useState } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { api } from "./api";
import { LibraryCollection } from "./LibraryCollection";
import { translator } from "./i18n";
import { sourceObservations } from "./sourceObservations";
import type { ResearchRecord } from "./types";

const t=translator("en"), sha="a".repeat(64), revision="1".repeat(64);
const response=(value:unknown)=>new Response(JSON.stringify(value),{status:200,headers:{"Content-Type":"application/json"}});
const saved={text:"Edited project working summary",artifact_id:"report-one",artifact_sha256:sha,source_revision:"2".repeat(64),previous_revision:revision,saved_at:"2026-11-03T00:00:00Z"};
function fixture() {
  const record:ResearchRecord={id:"source-one",kind:"source",data:{id:"one",title:"Synthetic chosen paper",category:"method",summary:"Original saved summary",abstract:"Original abstract",human_acceptance:"pending",reading_level:"abstract-snippet",source_records:[{observation_id:"obs-one",work_id:"one",source_id:"one",status:"available",evidence_level:"generated-summary",text_path:"report.md",text_sha256:sha}]}};
  const other:ResearchRecord={id:"source-other",kind:"source",data:{id:"other",title:"Synthetic other paper",category:"method"}};
  const artifact={id:"report-one",project_id:"project-one",source_record_id:record.id,path:"report.md",role:"evidence",sha256:sha,current:true};
  return {record,other,scope:{projectId:"project-one",artifacts:[artifact],active:true}};
}

it("saves, reloads and retains selected row and search/category filters while showing separate persisted working prose",async()=>{
  const f=fixture(),user=userEvent.setup();let stored=f.record;
  const fetch=vi.spyOn(globalThis,"fetch").mockImplementation(async(url,init)=>{
    const path=String(url);
    if(path.endsWith("/artifacts/report-one/text"))return response({ok:true,preview:{}});
    if(path.includes("/working-summary?") )return response({ok:true,context:{source_record_id:f.record.id,artifact_id:"report-one",artifact_sha256:sha,revision,draft_text:"Generated draft",working_summary:null}});
    if(path.endsWith("/working-summary") && init?.method==="POST") {
      stored={...f.record,data:{...f.record.data,working_summary:saved}};
      return response({ok:true,record:stored,reused:false});
    }
    if(path.endsWith("/projects/project-one"))return response({ok:true,records:[f.other,stored]});
    throw new Error("Unexpected synthetic request");
  });
  function Harness() {
    const [sources,setSources]=useState([f.other,f.record]);
    return <LibraryCollection sources={sources} screenings={[]} t={t} observationRead={f.scope} onScreen={vi.fn()} onPrepare={vi.fn()}
      onWorkingSummarySaved={async()=>{const result=await api<{ok:true;records:ResearchRecord[]}>("/projects/project-one");setSources(result.records);}}/>;
  }
  const {unmount}=render(<Harness/>);
  await user.click(screen.getByRole("button",{name:"method 2"}));await user.type(screen.getByRole("searchbox"),"Synthetic");
  const row=screen.getByRole("button",{name:f.record.data.title as string});await user.click(row);
  await user.click(screen.getByRole("button",{name:`${t("workingSummaryReview")} report-one`}));
  const input=await screen.findByRole("textbox",{name:t("workingSummaryText")});await user.clear(input);await user.type(input,saved.text);
  await user.click(screen.getByRole("button",{name:t("workingSummarySave")}));
  const working=await screen.findByRole("region",{name:t("workingSummaryTitle")});expect(within(working).getByText(saved.text)).toBeVisible();
  expect(screen.getByText("Original saved summary")).toBeVisible();expect(screen.getByRole("searchbox")).toHaveValue("Synthetic");
  expect(screen.getByRole("button",{name:"method 2"})).toHaveAttribute("aria-pressed","true");expect(row).toHaveAttribute("aria-pressed","true");
  expect(within(screen.getByRole("dialog")).getByRole("heading")).toHaveFocus();
  await user.click(screen.getByRole("button",{name:t("workingSummaryClose")}));expect(screen.getByRole("button",{name:`${t("workingSummaryReview")} report-one`})).toHaveFocus();
  expect(fetch.mock.calls.filter(c=>c[1]?.method==="POST")).toHaveLength(1);
  expect(stored.data.human_acceptance).toBe("pending");expect(stored.data.reading_level).toBe("abstract-snippet");
  expect(sourceObservations(stored).savedSummary).toBe("Original saved summary");
  unmount();
  render(<LibraryCollection sources={[stored]} screenings={[]} t={t} observationRead={f.scope} onScreen={vi.fn()} onPrepare={vi.fn()}/>);
  expect(within(screen.getByRole("region",{name:t("workingSummaryTitle")})).getByText(saved.text)).toBeVisible();
});

it("counts only structurally valid persisted working text as summary-present and retains original abstract precedence",()=>{
  const f=fixture();delete f.record.data.summary;delete f.record.data.abstract;
  const invalid={...f.other,data:{...f.other.data,working_summary:{...saved,source_revision:"invalid"}}};
  const valid={...f.record,data:{...f.record.data,working_summary:saved}};
  const {rerender}=render(<LibraryCollection sources={[valid,invalid]} screenings={[]} t={t} onScreen={vi.fn()} onPrepare={vi.fn()}/>);
  expect(screen.getByRole("button",{name:`${t("catalogNeedsSummary")} (1)`})).toBeVisible();
  expect(screen.getByText(saved.text)).toBeVisible();
  expect(sourceObservations(valid).savedSummary).toBeNull();
  rerender(<LibraryCollection sources={[{...valid,data:{...valid.data,abstract:"Original abstract"}}]} screenings={[]} t={t} onScreen={vi.fn()} onPrepare={vi.fn()}/>);
  expect(screen.getByText("Original abstract")).toBeVisible();expect(screen.getByText(saved.text)).toBeVisible();
});
