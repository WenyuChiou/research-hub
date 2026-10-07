import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api, auditProject } from "./api";
import {
  candidateArtifacts,
  DeliveryCard,
  deliveryEligible,
  DeliveryPanel,
} from "./Delivery";
import { translator } from "./i18n";
import { ManuscriptTools } from "./ManuscriptTools";
import { TaskCard } from "./Tasks";
import type { DeliveryAction, ProjectDetail, Task } from "./types";

const t = translator("en");
const sha = "a".repeat(64);
const task: Task = {
  id: "task-accepted",
  operation: "draft",
  mode: "handoff",
  status: "completed",
  action_hash: sha,
  result: { artifacts: [{ path: "candidates/draft.md", sha256: sha }] },
};
const detail: ProjectDetail = {
  ok: true,
  project: {
    id: "project-1",
    title: "Study",
    archetype: "empirical",
    goal: "Investigate.",
  },
  tasks: [task],
  actions: [],
  artifacts: [],
  records: [],
  manuscript: { authority_sources: ["local-writing-authority"], contract: {} },
  workflow: null,
  warnings: [],
};
const action: DeliveryAction = {
  id: "bundle-1",
  kind: "delivery_bundle",
  status: "awaiting_human",
  action_hash: sha,
  packet: { task_ids: [task.id], files: ["candidates/draft.md"] },
};
const response = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
function humanToken() {
  const token = document.createElement("meta");
  token.name = "research-hub-human-token";
  token.content = "human-test-only";
  document.head.append(token);
}

describe("manuscript authority integration", () => {
  it("preserves structured audit findings without accepting unrelated ok:false responses", async () => {
    const report = {
      ok: false,
      operation: "consistency",
      report: { findings: ["Evidence link missing"] },
      exit_code: 2,
      adapter_sha256: sha,
      semantic_acceptance: "not_performed",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async () => response(report)),
    );
    await expect(
      auditProject("project-1", { operation: "consistency" }),
    ).resolves.toEqual(report);
    await expect(
      api("/projects/project-1/audit", { operation: "consistency" }),
    ).rejects.toMatchObject({ name: "ApiError" });
  });
  it("still surfaces transport failures from the audit endpoint", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          response(
            {
              ok: false,
              error: "Writing adapter unavailable",
              code: "adapter_missing",
            },
            503,
          ),
        ),
    );
    await expect(
      auditProject("project-1", { operation: "state" }),
    ).rejects.toMatchObject({ code: "adapter_missing", status: 503 });
  });
  it("renders failed audit findings and the authority fingerprint, without generic saved success", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          response({
            ok: false,
            operation: "candidate",
            report: { findings: ["Missing evidence anchor"] },
            exit_code: 2,
            adapter_sha256: sha,
            semantic_acceptance: "not_performed",
          }),
        ),
    );
    render(<ManuscriptTools detail={detail} t={t} onSaved={async () => {}} />);
    await user.selectOptions(screen.getByLabelText(/^Check/), "candidate");
    await user.type(
      screen.getByLabelText(/Candidate path/),
      "candidates/draft.md",
    );
    await user.click(
      screen.getByRole("button", { name: /Run manuscript check/ }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Findings require attention",
    );
    expect(screen.getByText(/Missing evidence anchor/)).toBeInTheDocument();
    expect(screen.getByText(sha)).toBeInTheDocument();
    expect(
      screen.getByText("Semantic acceptance was not performed."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Saved to this project/)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Candidate path/)).toHaveValue(
      "candidates/draft.md",
    );
  });
  it("shows the bound state reference and marks stale acceptance from the impact report", async () => {
    const user = userEvent.setup();
    const fetch = vi
      .fn()
      .mockImplementation(async (url: string) =>
        url.endsWith("/bind")
          ? response({
              ok: true,
              path: "C:/study/.research/projects/project-1/manuscript_state.json",
              state: detail.manuscript,
            })
          : response({
              ok: true,
              impacts: [
                {
                  source: "evidence.md",
                  affected: ["claim-1"],
                  reason: "Source changed",
                },
              ],
              stale_tasks: [
                {
                  task_id: "task-accepted",
                  status: "completed",
                  reason: "Accepted input changed",
                  acceptance_current: false,
                },
              ],
              automatic_semantic_sync: false,
            }),
      );
    vi.stubGlobal("fetch", fetch);
    render(<ManuscriptTools detail={detail} t={t} onSaved={async () => {}} />);
    await user.click(
      screen.getByRole("button", { name: "Bind manuscript state" }),
    );
    expect(
      await screen.findByText(
        "C:/study/.research/projects/project-1/manuscript_state.json",
      ),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Inspect change impact" }),
    );
    expect(
      await screen.findByText("Acceptance is no longer current"),
    ).toBeInTheDocument();
    expect(screen.getByText("Accepted input changed")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});

describe("local proposal delivery", () => {
  it("requires accepted, current task results with candidate fingerprints", () => {
    expect(deliveryEligible(task)).toBe(true);
    expect(deliveryEligible({ ...task, status: "awaiting_human" })).toBe(false);
    expect(deliveryEligible({ ...task, acceptance_current: false })).toBe(
      false,
    );
    expect(deliveryEligible({ ...task, result: { artifacts: [] } })).toBe(
      false,
    );
    expect(
      candidateArtifacts({
        ...task,
        result: { artifacts: [{ path: "draft.md", sha256: "bad" }] },
      }),
    ).toEqual([]);
  });
  it("prepares only the selected task IDs and never executes automatically", async () => {
    const user = userEvent.setup();
    const fetch = vi.fn().mockResolvedValue(response({ ok: true, action }));
    vi.stubGlobal("fetch", fetch);
    const onSaved = vi.fn().mockResolvedValue(undefined);
    render(
      <DeliveryPanel
        projectId="project-1"
        tasks={[
          task,
          { ...task, id: "task-pending", status: "awaiting_human" },
        ]}
        actions={[]}
        t={t}
        onSaved={onSaved}
      />,
    );
    expect(screen.getAllByRole("checkbox")).toHaveLength(1);
    await user.click(screen.getByRole("checkbox"));
    await user.click(
      screen.getByRole("button", { name: /Prepare local bundle/ }),
    );
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/projects/project-1/delivery");
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
      task_ids: ["task-accepted"],
    });
  });
  it("shows a CLI hint without human authorization and never offers execution before approval", () => {
    render(<DeliveryCard action={action} t={t} onSaved={async () => {}} />);
    expect(
      screen.getByRole("button", { name: "Record decision" }),
    ).toBeDisabled();
    expect(
      screen.getByText(/research-hub action decide bundle-1/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Create approved local ZIP" }),
    ).not.toBeInTheDocument();
  });
  it("sends human proof only for the action decision and leaves execution separate", async () => {
    humanToken();
    const user = userEvent.setup();
    const fetch = vi
      .fn()
      .mockResolvedValue(
        response({ ok: true, action: { ...action, status: "approved" } }),
      );
    vi.stubGlobal("fetch", fetch);
    const onSaved = vi.fn().mockResolvedValue(undefined);
    render(<DeliveryCard action={action} t={t} onSaved={onSaved} />);
    await user.selectOptions(screen.getByLabelText(/^Outcome/), "accept");
    await user.type(screen.getByLabelText(/Reviewer name/), "Researcher");
    await user.type(
      screen.getByLabelText(/Rationale/),
      "Candidate files reviewed for local handoff.",
    );
    await user.click(screen.getByRole("button", { name: /Record decision/ }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/actions/bundle-1/decision");
    expect(fetch.mock.calls[0][1].headers["X-Human-Token"]).toBe(
      "human-test-only",
    );
    expect(JSON.parse(fetch.mock.calls[0][1].body).action_hash).toBe(sha);
  });
  it("executes only an approved action, reconciles completed actions, and displays a local receipt without a download link", async () => {
    humanToken();
    const user = userEvent.setup();
    const fetch = vi
      .fn()
      .mockImplementation(async () =>
        response({ ok: true, action: { ...action, status: "completed" } }),
      );
    vi.stubGlobal("fetch", fetch);
    const onSaved = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(
      <DeliveryCard
        action={{ ...action, status: "approved" }}
        t={t}
        onSaved={onSaved}
      />,
    );
    await user.click(
      screen.getByRole("button", { name: "Create approved local ZIP" }),
    );
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(fetch.mock.calls[0][1].headers["X-Human-Token"]).toBeUndefined();
    rerender(
      <DeliveryCard
        action={{
          ...action,
          status: "completed",
          receipt: {
            path: "C:/study/proposal.zip",
            sha256: sha,
            verified_at: "2026-09-08T01:00:00Z",
          },
        }}
        t={t}
        onSaved={onSaved}
      />,
    );
    expect(screen.getByText("C:/study/proposal.zip")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Create approved local ZIP" }),
    ).not.toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Inspect execution receipt" }),
    );
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(2));
    expect(fetch.mock.calls[1][0]).toBe("/api/v1/actions/bundle-1/reconcile");
  });
});

describe("explicit task recovery", () => {
  it("offers cancellation only for a nonterminal task and recovery only while running", async () => {
    const user = userEvent.setup();
    const fetch = vi
      .fn()
      .mockResolvedValue(
        response({ ok: true, task: { ...task, status: "awaiting_agent" } }),
      );
    vi.stubGlobal("fetch", fetch);
    const onSaved = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(
      <TaskCard
        task={{ ...task, status: "running" }}
        t={t}
        approvalMessage="CLI"
        onSaved={onSaved}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Cancel task" }),
    ).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
    await user.click(
      screen.getByText("Interrupted-run recovery", { selector: "summary" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Inspect interrupted run" }),
    );
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/tasks/task-accepted/recover");
    rerender(
      <TaskCard task={task} t={t} approvalMessage="CLI" onSaved={onSaved} />,
    );
    expect(
      screen.queryByRole("button", { name: "Cancel task" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("Interrupted-run recovery"),
    ).not.toBeInTheDocument();
  });
});
