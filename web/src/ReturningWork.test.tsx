import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { ReturningWork, recentSavedTasks } from "./ReturningWork";
import { translator } from "./i18n";

afterEach(() => vi.unstubAllGlobals());
import type { ProjectDetail, Task, Workspace } from "./types";

const project = {
  id: "river-study",
  title: "River study",
  archetype: "empirical" as const,
  goal: "Compare public evidence",
};
const workspace: Workspace = {
  ok: true,
  projects: [project],
  capabilities: {
    codex: { status: "unavailable", message: "Unavailable" },
    writing: { status: "unavailable", message: "Unavailable" },
    approval: { status: "unavailable", message: "Unavailable" },
  },
  protection_scope: "Local proposals only",
};
const makeTask = (
  id: string,
  updated_at?: string,
  status = "awaiting_agent",
): Task => ({
  id,
  updated_at,
  status,
  operation: "frame",
  mode: "handoff",
  action_hash: "a".repeat(64),
});
const detail: ProjectDetail = {
  ok: true,
  project,
  tasks: [],
  actions: [],
  records: [],
  artifacts: [],
  manuscript: null,
  workflow: null,
  warnings: [],
};
function serve(value: ProjectDetail, projects = workspace.projects) {
  const fetch = vi.fn(
    async (input: RequestInfo | URL, _options?: RequestInit) =>
      new Response(
        JSON.stringify(
          String(input).endsWith("/workspace")
            ? { ...workspace, projects }
            : value,
        ),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
  );
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
function overview() {
  return screen
    .getByRole("heading", { name: "Task activity" })
    .closest("section")!;
}

describe("returning selected-project work", () => {
  it("orders by saved task update, including an older-created task outside the first five", async () => {
    serve({
      ...detail,
      tasks: [
        makeTask("created-last", "2026-10-20T00:00:00Z"),
        ...[1, 2, 3, 4].map((n) =>
          makeTask(`middle-${n}`, `2026-10-1${n}T00:00:00Z`),
        ),
        makeTask("updated-last", "2026-10-24T00:00:00Z"),
      ],
    });
    render(<App />);
    await screen.findByRole("heading", { name: "Task activity" });
    expect(
      within(overview())
        .getAllByText(/^(updated-last|created-last|middle-\d)$/)
        .map((node) => node.textContent),
    ).toEqual([
      "updated-last",
      "created-last",
      "middle-4",
      "middle-3",
      "middle-2",
    ]);
    expect(within(overview()).getByText("2026-10-24T00:00:00Z")).toBeVisible();
  });
  it("opens the exact chosen task and returns to the same project without writes", async () => {
    const fetch = serve({
      ...detail,
      tasks: [
        makeTask("chosen-task", "2026-10-24T00:00:00Z"),
        makeTask("other-task"),
      ],
    });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: "Task activity" });
    await user.click(
      within(overview()).getByRole("button", { name: "Open task chosen-task" }),
    );
    await waitFor(() =>
      expect(document.getElementById("review-task-chosen-task")).toHaveFocus(),
    );
    await user.click(
      screen.getByRole("button", { name: "Back to project overview" }),
    );
    expect(
      screen.getByRole("combobox", { name: "Choose a project" }),
    ).toHaveValue(project.id);
    expect(within(overview()).getByText("chosen-task")).toBeVisible();
    await user.click(screen.getByRole("button", { name: /New project/ }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(within(overview()).getByText("chosen-task")).toBeVisible();
    expect(
      fetch.mock.calls.every(
        (call) => !call[1]?.method || call[1].method === "GET",
      ),
    ).toBe(true);
    expect(
      fetch.mock.calls.every(
        (call) =>
          String(call[0]).includes("/workspace") ||
          String(call[0]).includes("/projects/river-study"),
      ),
    ).toBe(true);
  });
});

describe("saved-state projection boundaries", () => {
  it("sorts missing and malformed timestamps last without mutating API data", () => {
    const tasks = [
      makeTask("missing"),
      makeTask("invalid", "not-a-date"),
      makeTask("valid", "2026-10-23T23:00:00Z"),
    ];
    expect(recentSavedTasks(tasks).map((task) => task.id)).toEqual([
      "valid",
      "missing",
      "invalid",
    ]);
    expect(tasks.map((task) => task.id)).toEqual([
      "missing",
      "invalid",
      "valid",
    ]);
  });
  it("keeps human acceptance distinct from unknown external delivery and historical local receipts", () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    render(
      <ReturningWork
        detail={{
          ...detail,
          tasks: [makeTask("accepted", undefined, "completed")],
          actions: [
            {
              id: "pending",
              kind: "delivery_bundle",
              status: "pending_external_action",
              action_hash: "a",
              packet: {},
            },
            {
              id: "done",
              kind: "delivery_bundle",
              status: "completed",
              action_hash: "b",
              packet: {},
              receipt: {
                path: ".research/deliveries/public-fixture.zip",
                sha256: "a".repeat(64),
                verified_at: "2026-10-20T00:00:00Z",
              },
            },
          ],
        }}
        t={translator("en")}
        navigate={vi.fn()}
      />,
    );
    expect(screen.getByText("Accepted by human")).toBeVisible();
    expect(screen.getByText("Pending local action")).toBeVisible();
    expect(screen.getByText(/external delivery is unknown here/)).toBeVisible();
    expect(screen.getByText(/No local receipt recorded/)).toBeVisible();
    expect(screen.getByText(/has not been re-verified/)).toBeVisible();
    expect(
      screen.getByText(".research/deliveries/public-fixture.zip"),
    ).toBeVisible();
    expect(fetch).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("button", { name: /retry|create|approve/i }),
    ).not.toBeInTheDocument();
  });
  it("offers the actual source-record path without accounts or a fictional reader", async () => {
    const navigate = vi.fn();
    render(
      <ReturningWork
        detail={detail}
        t={translator("en")}
        navigate={navigate}
      />,
    );
    expect(
      screen.getByText(
        /registering a source does not mean its full text has been read/,
      ),
    ).toBeVisible();
    expect(screen.getByText(/No local bundle actions recorded/)).toBeVisible();
    await userEvent.setup().click(
      screen.getByRole("button", {
        name: translator("en")("viewLiterature"),
      }),
    );
    expect(navigate).toHaveBeenCalledWith("literature");
  });
  it("bounds local actions to five and navigates to the existing local delivery panel", async () => {
    const navigate = vi.fn();
    render(
      <ReturningWork
        detail={{
          ...detail,
          actions: Array.from({ length: 8 }, (_, i) => ({
            id: `bundle-${i}`,
            kind: "delivery_bundle" as const,
            status: "cancelled" as const,
            action_hash: "a",
            packet: {},
          })),
        }}
        t={translator("en")}
        navigate={navigate}
      />,
    );
    expect(screen.getAllByText(/^bundle-/)).toHaveLength(5);
    await userEvent
      .setup()
      .click(
        screen.getByRole("button", { name: "Inspect local bundle actions" }),
      );
    expect(navigate).toHaveBeenCalledWith("review", "review-local-delivery");
  });
  it("shows explicit unknown update time in Traditional Chinese", () => {
    render(
      <ReturningWork
        detail={{ ...detail, tasks: [makeTask("public-task")] }}
        t={translator("zh-TW")}
        navigate={vi.fn()}
      />,
    );
    expect(screen.getByText(/任務最後更新.*未知／未記錄/)).toBeVisible();
    expect(
      screen.getByRole("button", { name: "開啟任務 public-task" }),
    ).toBeVisible();
  });
});

function holdFrames() {
  const frames = new Map<number, FrameRequestCallback>();
  let id = 0;
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    frames.set(++id, callback);
    return id;
  });
  vi.stubGlobal("cancelAnimationFrame", (key: number) => frames.delete(key));
  return {
    frames,
    flush: () =>
      act(() => {
        const callbacks = [...frames.values()];
        frames.clear();
        callbacks.forEach((callback) => callback(0));
      }),
  };
}

describe("interrupted return navigation", () => {
  it("reports a task removed by refresh instead of focusing another task", async () => {
    const { frames, flush } = holdFrames();
    serve({
      ...detail,
      tasks: [makeTask("removed-task"), makeTask("other-task")],
    });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: "Task activity" });
    await user.click(
      within(overview()).getByRole("button", {
        name: "Open task removed-task",
      }),
    );
    await waitFor(() => expect(frames.size).toBe(1));
    serve({ ...detail, tasks: [makeTask("other-task")] });
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() =>
      expect(document.getElementById("review-task-removed-task")).toBeNull(),
    );
    flush();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "The selected task is no longer present in this project",
    );
    expect(document.getElementById("review-task-other-task")).not.toHaveFocus();
    expect(screen.getByRole("heading", { level: 1 })).toHaveFocus();
  });
  it("clears queued task focus on project switch and returns within the new project", async () => {
    const second = { ...project, id: "second-study", title: "Second study" };
    const { frames, flush } = holdFrames();
    serve({ ...detail, tasks: [makeTask("same-id")] }, [project, second]);
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: "Task activity" });
    await user.click(
      within(overview()).getByRole("button", { name: "Open task same-id" }),
    );
    await waitFor(() => expect(frames.size).toBe(1));
    serve({ ...detail, project: second, tasks: [makeTask("same-id")] }, [
      project,
      second,
    ]);
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Choose a project" }),
      second.id,
    );
    await screen.findByText("Second study", { selector: ".breadcrumb strong" });
    flush();
    expect(document.getElementById("review-task-same-id")).not.toHaveFocus();
    await user.click(
      screen.getByRole("button", { name: "Back to project overview" }),
    );
    expect(
      screen.getByRole("combobox", { name: "Choose a project" }),
    ).toHaveValue(second.id);
    expect(within(overview()).getByText("Second study")).toBeVisible();
  });
  it("honors newer hash navigation without a false missing-task warning", async () => {
    const { frames, flush } = holdFrames();
    serve({ ...detail, tasks: [makeTask("task")] });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: "Task activity" });
    await user.click(
      within(overview()).getByRole("button", { name: "Open task task" }),
    );
    await waitFor(() => expect(frames.size).toBe(1));
    act(() => {
      window.history.replaceState({}, "", "#overview");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    flush();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Overview",
    );
    expect(screen.getByRole("heading", { level: 1 })).toHaveFocus();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
