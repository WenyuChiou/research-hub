import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import App from "./App";
import { READ_TIMEOUT_MS } from "./api";
import type { ProjectDetail, Task, Workspace } from "./types";

const task: Task = {
  id: "task-1",
  operation: "outline",
  mode: "connected",
  status: "running",
  action_hash: "a".repeat(64),
};
const detail: ProjectDetail = {
  ok: true,
  project: {
    id: "study",
    title: "Study",
    archetype: "empirical",
    goal: "Original project goal",
  },
  records: [],
  artifacts: [],
  tasks: [task],
  actions: [],
  manuscript: null,
  workflow: null,
  warnings: [],
};
const other: ProjectDetail = {
  ...detail,
  project: {
    ...detail.project,
    id: "other",
    title: "Other study",
    goal: "Other project goal",
  },
  tasks: [],
};
const workspace: Workspace = {
  ok: true,
  projects: [detail.project, other.project],
  capabilities: {
    approval: { status: "unavailable", message: "Mock only" },
    codex: { status: "unavailable", message: "Mock only" },
    writing: { status: "unavailable", message: "Mock only" },
  },
  protection_scope: "Mock only",
};
const response = (value: unknown) =>
  new Response(JSON.stringify(value), {
    headers: { "Content-Type": "application/json" },
  });
const advance = async (ms: number) => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
};
let reads: ReturnType<
  typeof vi.fn<(options: RequestInit) => Promise<Response>>
>;
let fetchMock: ReturnType<
  typeof vi.fn<(url: string, options: RequestInit) => Promise<Response>>
>;
let projectReads: ReturnType<
  typeof vi.fn<(options: RequestInit) => Promise<Response>>
>;
async function mount() {
  let view!: ReturnType<typeof render>;
  await act(async () => {
    view = render(<App />);
  });
  return view;
}
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
  vi.setSystemTime(new Date("2026-10-22T00:00:00Z"));
  reads = vi.fn().mockImplementation(async () => response({ ok: true, task }));
  projectReads = vi.fn().mockImplementation(async () => response(detail));
  fetchMock = vi
    .fn()
    .mockImplementation((url: string, options: RequestInit) => {
      if (url === "/api/v1/workspace")
        return Promise.resolve(response(workspace));
      if (url === "/api/v1/projects/study") return projectReads(options);
      if (url === "/api/v1/projects/other")
        return Promise.resolve(response(other));
      if (url === "/api/v1/tasks/task-1") return reads(options);
      if (url === "/api/v1/tasks/task-1/cancel")
        return Promise.resolve(
          response({ ok: true, task: { ...task, status: "cancelled" } }),
        );
      throw new Error(`Unexpected request: ${url}`);
    });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("read polling recovery", () => {
  it("marks a hung read stale, retries after timeout, and ignores its late completion", async () => {
    let resolve!: (value: Response) => void;
    reads.mockImplementationOnce(() => new Promise<Response>(yes => { resolve = yes; }));
    const view = await mount();
    await advance(3000);
    await advance(READ_TIMEOUT_MS);
    expect(screen.getByRole("alert")).toHaveTextContent("Updates are delayed");
    expect((reads.mock.calls[0][0].signal as AbortSignal).aborted).toBe(true);
    await advance(3000);
    expect(reads).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await act(async () => { resolve(response({ ok: true, task: { ...task, status: "completed" } })); });
    expect(projectReads).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls.every(([, options]) => options.method === "GET")).toBe(true);
    view.unmount();
  });

  it("recovers when task response headers arrive but the body hangs", async () => {
    reads.mockResolvedValueOnce({ json: () => new Promise(() => {}) } as Response);
    const view = await mount();
    await advance(3000 + READ_TIMEOUT_MS);
    expect(screen.getByRole("alert")).toHaveTextContent("Updates are delayed");
    await advance(3000);
    expect(reads).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("retries a timed-out terminal-task detail refresh", async () => {
    const view = await mount();
    reads.mockImplementation(async () => response({ ok: true, task: { ...task, status: "completed" } }));
    projectReads.mockImplementationOnce(() => new Promise(() => {}));
    projectReads.mockImplementation(async () => response({ ...detail, tasks: [] }));
    await advance(3000 + READ_TIMEOUT_MS);
    expect(screen.getByRole("alert")).toHaveTextContent("Updates are delayed");
    await advance(3000);
    expect(projectReads).toHaveBeenCalledTimes(3);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("switching project cancels a hung read deadline without stale error", async () => {
    reads.mockImplementationOnce(() => new Promise(() => {}));
    const view = await mount();
    await advance(3000);
    await act(async () => {
      fireEvent.change(screen.getByRole("combobox", { name: "Choose a project" }), { target: { value: "other" } });
    });
    await advance(READ_TIMEOUT_MS * 2);
    expect(screen.getByText("Other project goal")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(reads).toHaveBeenCalledTimes(1);
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("recovers after a transient read failure without replaying mutations", async () => {
    reads.mockRejectedValueOnce(new Error("temporary outage"));
    const view = await mount();
    await advance(3000);
    expect(reads).toHaveBeenCalledTimes(1);
    await advance(3000);
    expect(reads).toHaveBeenCalledTimes(2);
    await advance(3000);
    expect(reads).toHaveBeenCalledTimes(3);
    expect(
      fetchMock.mock.calls.every(([, options]) => options.method === "GET"),
    ).toBe(true);
    view.unmount();
  });

  it("backs off to 30 seconds, retains last-success time, and resets after recovery", async () => {
    const view = await mount();
    await advance(3000);
    reads.mockRejectedValue(new Error("offline"));
    await advance(3000);
    expect(screen.getByRole("alert")).toHaveTextContent("Updates are delayed");
    expect(screen.getByRole("alert").querySelector("time")).toHaveAttribute(
      "dateTime",
      "2026-10-22T00:00:03.000Z",
    );
    for (const delay of [3000, 6000, 12000, 24000, 30000, 30000]) {
      const count = reads.mock.calls.length;
      await advance(delay - 1);
      expect(reads).toHaveBeenCalledTimes(count);
      await advance(1);
      expect(reads).toHaveBeenCalledTimes(count + 1);
    }
    reads.mockImplementation(async () => response({ ok: true, task }));
    await advance(30000);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    const count = reads.mock.calls.length;
    await advance(3000);
    expect(reads).toHaveBeenCalledTimes(count + 1);
    view.unmount();
  });

  it("retries a failed terminal-task detail refresh and stops after recovery", async () => {
    const view = await mount();
    reads.mockImplementation(async () =>
      response({ ok: true, task: { ...task, status: "awaiting_human" } }),
    );
    projectReads.mockRejectedValueOnce(new Error("refresh failed"));
    projectReads.mockImplementation(async () =>
      response({ ...detail, tasks: [{ ...task, status: "awaiting_human" }] }),
    );
    await advance(3000);
    await advance(3000);
    expect(projectReads).toHaveBeenCalledTimes(3);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await advance(60000);
    expect(reads).toHaveBeenCalledTimes(2);
    view.unmount();
  });

  it.each(["resolve", "reject"])(
    "ignores a late task %s after a project change",
    async (outcome) => {
      let resolve!: (value: Response) => void;
      let reject!: (reason: Error) => void;
      reads.mockImplementation(
        () =>
          new Promise<Response>((yes, no) => {
            resolve = yes;
            reject = no;
          }),
      );
      const view = await mount();
      await advance(3000);
      const signal = reads.mock.calls[0][0].signal as AbortSignal;
      await act(async () => {
        fireEvent.change(
          screen.getByRole("combobox", { name: "Choose a project" }),
          { target: { value: "other" } },
        );
      });
      expect(signal.aborted).toBe(true);
      await act(async () => {
        if (outcome === "resolve")
          resolve(
            response({ ok: true, task: { ...task, status: "completed" } }),
          );
        else reject(new Error("late failure"));
      });
      expect(screen.getByText("Other project goal")).toBeInTheDocument();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      await advance(60000);
      expect(reads).toHaveBeenCalledTimes(1);
      expect(projectReads).toHaveBeenCalledTimes(1);
      view.unmount();
    },
  );

  it("ignores a late terminal-task detail refresh after switching projects", async () => {
    let resolve!: (value: Response) => void;
    const view = await mount();
    reads.mockImplementation(async () =>
      response({ ok: true, task: { ...task, status: "completed" } }),
    );
    projectReads.mockImplementation(
      () =>
        new Promise<Response>((yes) => {
          resolve = yes;
        }),
    );
    await advance(3000);
    const signal = projectReads.mock.calls[1][0].signal as AbortSignal;
    await act(async () => {
      fireEvent.change(
        screen.getByRole("combobox", { name: "Choose a project" }),
        { target: { value: "other" } },
      );
    });
    expect(signal.aborted).toBe(true);
    await act(async () => {
      resolve(response({ ...detail, tasks: [] }));
    });
    expect(screen.getByText("Other project goal")).toBeInTheDocument();
    await advance(60000);
    expect(reads).toHaveBeenCalledTimes(1);
    view.unmount();
  });

  it("aborts an in-flight read and ignores its late rejection after unmount", async () => {
    let reject!: (reason: Error) => void;
    reads.mockImplementation(
      () =>
        new Promise<Response>((_, no) => {
          reject = no;
        }),
    );
    const view = await mount();
    await advance(3000);
    const signal = reads.mock.calls[0][0].signal as AbortSignal;
    view.unmount();
    expect(signal.aborted).toBe(true);
    await act(async () => {
      reject(new Error("late outage"));
    });
    await advance(60000);
    expect(reads).toHaveBeenCalledTimes(1);
  });

  it("clears stale status after an explicit cancellation refresh without replaying it", async () => {
    window.history.replaceState({}, "", "/#review");
    reads.mockRejectedValue(new Error("offline"));
    const view = await mount();
    await advance(3000);
    expect(screen.getByRole("alert")).toHaveTextContent("Updates are delayed");
    projectReads.mockImplementation(async () =>
      response({ ...detail, tasks: [{ ...task, status: "cancelled" }] }),
    );
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Cancel task" }));
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await advance(60000);
    expect(reads).toHaveBeenCalledTimes(1);
    const posts = fetchMock.mock.calls.filter(
      ([, options]) => options.method === "POST",
    );
    expect(posts).toHaveLength(1);
    expect(posts[0][0]).toBe("/api/v1/tasks/task-1/cancel");
    view.unmount();
  });

  it("aborts pending sibling reads before retrying a failed multi-task batch", async () => {
    const signals: AbortSignal[] = [];
    projectReads.mockImplementation(async () =>
      response({ ...detail, tasks: [task, { ...task, id: "task-2" }] }),
    );
    const original = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((url: string, options: RequestInit) => {
      if (url !== "/api/v1/tasks/task-2") return original(url, options);
      const signal = options.signal as AbortSignal;
      signals.push(signal);
      return new Promise<Response>((_, reject) => {
        signal.addEventListener(
          "abort",
          () => reject(new DOMException("Aborted", "AbortError")),
          { once: true },
        );
      });
    });
    reads.mockRejectedValue(new Error("one task unavailable"));
    const view = await mount();
    await advance(3000);
    expect(signals).toHaveLength(1);
    expect(signals[0].aborted).toBe(true);
    await advance(3000);
    expect(signals).toHaveLength(2);
    expect(signals[1]).not.toBe(signals[0]);
    expect(signals.every((signal) => signal.aborted)).toBe(true);
    view.unmount();
  });

  it.each([401, 403, 404, 200])(
    "stops automatic retries for permanent API error %s and allows manual refresh",
    async (status) => {
      reads.mockImplementation(
        async () =>
          new Response(
            JSON.stringify({
              ok: false,
              error: "Permission or contract error",
              code: "request_failed",
            }),
            { status },
          ),
      );
      const view = await mount();
      await advance(3000);
      expect(screen.getByRole("alert")).toHaveTextContent("Updates stopped");
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Permission or contract error",
      );
      await advance(60000);
      expect(reads).toHaveBeenCalledTimes(1);
      reads.mockImplementation(async () => response({ ok: true, task }));
      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
      });
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      await advance(3000);
      expect(reads).toHaveBeenCalledTimes(2);
      view.unmount();
    },
  );

  it.each([408, 429, 503])(
    "recovers from retryable HTTP %s",
    async (status) => {
      reads.mockResolvedValueOnce(
        new Response(
          JSON.stringify({ ok: false, error: "Temporary server failure" }),
          { status },
        ),
      );
      const view = await mount();
      await advance(3000);
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Temporary server failure",
      );
      await advance(3000);
      expect(reads).toHaveBeenCalledTimes(2);
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      view.unmount();
    },
  );

  it("does not automatically retry an unreadable successful HTTP response", async () => {
    reads.mockImplementation(
      async () => new Response("not JSON", { status: 200 }),
    );
    const view = await mount();
    await advance(3000);
    expect(screen.getByRole("alert")).toHaveTextContent("Updates stopped");
    expect(screen.getByRole("alert")).toHaveTextContent("unreadable response");
    await advance(60000);
    expect(reads).toHaveBeenCalledTimes(1);
    view.unmount();
  });

  it("cancels a pending retry on unmount", async () => {
    reads.mockRejectedValue(new Error("offline"));
    const view = await mount();
    await advance(3000);
    view.unmount();
    await advance(60000);
    expect(reads).toHaveBeenCalledTimes(1);
  });
});
