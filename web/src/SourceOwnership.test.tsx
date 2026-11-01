import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AbstractDraftComposer } from "./AbstractDraft";
import { readableArtifact } from "./sourceStorage";
import { translator } from "./i18n";
import type { Artifact } from "./types";

const file: Artifact = {id:"owned",path:"owned.md",role:"evidence",sha256:"a".repeat(64),current:true,project_id:"project",source_record_id:"source-a"};
describe("filesystem source ownership", () => {
  it("offers only this source's owned evidence and genuinely unbound legacy files", () => {
    const legacy: Artifact = {id:"legacy",path:"legacy.md",role:"evidence",sha256:"b".repeat(64),current:true};
    render(<AbstractDraftComposer projectId="project" source={{id:"source-b",kind:"source",data:{title:"Source B",locator:"https://example.invalid/b"}}} artifacts={[file,legacy]}
      capability={{status:"unavailable",message:"Synthetic"}} t={translator("en")} onPrepared={vi.fn()} onCancel={vi.fn()} />);
    const options = within(screen.getByLabelText(translator("en")("abstractChooseFile"))).getAllByRole("option");
    expect(options.some(o => o.getAttribute("value") === "owned")).toBe(false);
    expect(options.some(o => o.getAttribute("value") === "legacy")).toBe(true);
  });
  it.each([null,"",0,{}," source-a "])("rejects malformed or nonexact owner %j", owner => {
    expect(readableArtifact({...file,source_record_id:owner} as unknown as Artifact,"project","source-a")).toBe(false);
  });
  it("retains exact-owner and unbound legacy access without a project escape", () => {
    expect(readableArtifact(file,"project","source-a")).toBe(true);
    expect(readableArtifact(file,"other","source-a")).toBe(false);
    const {source_record_id: _owner,...legacy} = file;
    expect(readableArtifact(legacy,"project","source-b")).toBe(true);
  });
});
