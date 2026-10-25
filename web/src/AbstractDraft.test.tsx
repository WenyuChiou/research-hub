import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  AbstractDraftComposer,
  AbstractDraftReview,
  originalRange,
  type TextPreview,
} from "./AbstractDraft";
import { TaskCard } from "./Tasks";
import App from "./App";
import { translator } from "./i18n";
import type {
  Artifact,
  ProjectDetail,
  ResearchRecord,
  Task,
  Workspace,
} from "./types";

const t = translator("en");
const source: ResearchRecord = {
  id: "source-a",
  kind: "source",
  data: { title: "Public river paper", locator: "https://example.org/river" },
};
const artifact: Artifact = {
  id: "evidence-a",
  path: "evidence/river.md",
  role: "evidence",
  sha256: "a".repeat(64),
  current: true,
};
const preview: TextPreview = {
  artifact_id: artifact.id,
  path: artifact.path,
  sha256: artifact.sha256,
  text: "Title\r\n😀 Abstract: A.\rEnd",
  codepoint_length: 25,
  bytes_read: 28,
  truncated: false,
};
const task: Task = {
  id: "draft-task",
  operation: "paper-abstract-draft",
  mode: "connected",
  status: "ready",
  action_hash: "b".repeat(64),
  request: {
    research_draft: {
      source_pack: {
        artifact_id: artifact.id,
        source_record_id: source.id,
        source_sha256: artifact.sha256,
        start: 7,
        end: 21,
        text: "😀 Abstract: A.",
        text_sha256: "c".repeat(64),
        source: {
          title: String(source.data.title),
          locator: String(source.data.locator),
          identity_status: "unverified",
          publication_version: "unknown",
        },
        scope: "abstract",
        scope_basis: "operator selection",
        truncated: false,
      },
    },
  },
};
const response = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
const renderComposer = (
  extra: Partial<Parameters<typeof AbstractDraftComposer>[0]> = {},
) =>
  render(
    <AbstractDraftComposer
      projectId="river"
      source={source}
      artifacts={[artifact]}
      capability={{ status: "unavailable", message: "Unavailable" }}
      t={t}
      onPrepared={vi.fn()}
      onCancel={vi.fn()}
      {...extra}
    />,
  );
async function readPreview() {
  const user = userEvent.setup();
  await user.selectOptions(
    screen.getByLabelText(t("abstractChooseFile")),
    artifact.id,
  );
  await user.click(screen.getByRole("button", { name: t("abstractReadText") }));
  return screen.findByLabelText(
    t("abstractText"),
  ) as Promise<HTMLTextAreaElement>;
}
function selectPassage(textarea: HTMLTextAreaElement, start = 6, end = 21) {
  act(() => {
    textarea.focus();
    textarea.setSelectionRange(start, end);
    fireEvent.select(textarea);
  });
}
afterEach(() => vi.unstubAllGlobals());

describe("original Unicode source selection", () => {
  it("maps normalized CRLF/lone CR plus astral UTF16 boundaries to original codepoints", () => {
    expect(originalRange("A\r\n😀B\rC", 2, 5)).toEqual({ start: 3, end: 5 });
    expect(originalRange("A\r\n😀B\rC", 5, 7)).toEqual({ start: 5, end: 7 });
    expect(originalRange("A\r\n😀B\rC", 0, 7)).toEqual({ start: 0, end: 7 });
  });
  it("rejects empty/out-of-bounds/mid-surrogate selections instead of shifting silently", () => {
    expect(originalRange("😀A", 1, 3)).toBeNull();
    expect(originalRange("😀A", 0, 1)).toBeNull();
    expect(originalRange("abc", 0, 4)).toBeNull();
    expect(originalRange("abc", 2, 2)).toBeNull();
    expect(originalRange("abc", -1, 2)).toBeNull();
  });
  it("preserves combining characters and original CRLF without rewriting the selected bytes", () => {
    const raw = "e\u0301\r\n𠮷\nZ";
    const selected = originalRange(raw, 0, 5)!;
    expect(selected).toEqual({ start: 0, end: 5 });
    expect(Array.from(raw).slice(selected.start, selected.end).join("")).toBe(
      "e\u0301\r\n𠮷",
    );
  });
});

describe("explicit selected-only abstract preparation", () => {
  it("does not read automatically, requires a passage, reuses IDs internally and prepares without running", async () => {
    const prepared = vi.fn();
    const fetch = vi.fn(
      async (input: RequestInfo | URL, options?: RequestInit) =>
        response(
          options?.method === "POST"
            ? { ok: true, task }
            : { ok: true, preview },
        ),
    );
    vi.stubGlobal("fetch", fetch);
    renderComposer({ onPrepared: prepared });
    expect(fetch).not.toHaveBeenCalled();
    const textarea = await readPreview();
    expect(textarea.value).toBe("Title\n😀 Abstract: A.\nEnd");
    expect(
      screen.getByRole("button", { name: t("abstractPrepare") }),
    ).toBeDisabled();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    selectPassage(textarea);
    expect(
      screen.getByRole("button", { name: t("abstractPrepare") }),
    ).toBeEnabled();
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: t("abstractPrepare") }));
    expect(prepared).toHaveBeenCalledWith(task);
    expect(fetch).toHaveBeenCalledTimes(2);
    const body = JSON.parse(String(fetch.mock.calls[1][1]?.body));
    expect(body).toEqual({
      operation: "paper-abstract-draft",
      mode: "connected",
      instructions: "",
      source_selection: {
        artifact_id: artifact.id,
        source_record_id: source.id,
        start: 7,
        end: 21,
      },
    });
    expect(
      fetch.mock.calls.some((call) => String(call[0]).includes("/run")),
    ).toBe(false);
  });
  it("clears old preview/range on file change and ignores a cancelled late response", async () => {
    let resolve!: (value: Response) => void;
    const fetch = vi.fn(
      () =>
        new Promise<Response>((done) => {
          resolve = done;
        }),
    );
    vi.stubGlobal("fetch", fetch);
    renderComposer({
      artifacts: [
        artifact,
        { ...artifact, id: "evidence-b", path: "evidence/second.txt" },
      ],
    });
    const user = userEvent.setup();
    await user.selectOptions(
      screen.getByLabelText(t("abstractChooseFile")),
      artifact.id,
    );
    await user.click(
      screen.getByRole("button", { name: t("abstractReadText") }),
    );
    await user.selectOptions(
      screen.getByLabelText(t("abstractChooseFile")),
      "evidence-b",
    );
    await act(async () => resolve(response({ ok: true, preview })));
    expect(screen.queryByLabelText(t("abstractText"))).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: t("abstractPrepare") }),
    ).not.toBeInTheDocument();
  });
  it("unmounts a source preview without reusing its late text in another source", async () => {
    let resolve!: (value: Response) => void;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise<Response>((done) => {
            resolve = done;
          }),
      ),
    );
    const props = {
      projectId: "river",
      source,
      artifacts: [artifact],
      capability: { status: "unavailable", message: "" },
      t,
      onPrepared: vi.fn(),
      onCancel: vi.fn(),
    };
    const view = render(<AbstractDraftComposer key="a" {...props} />);
    const user = userEvent.setup();
    await user.selectOptions(
      screen.getByLabelText(t("abstractChooseFile")),
      artifact.id,
    );
    await user.click(
      screen.getByRole("button", { name: t("abstractReadText") }),
    );
    view.rerender(
      <AbstractDraftComposer
        key="b"
        {...props}
        source={{
          ...source,
          id: "source-b",
          data: { ...source.data, title: "Second paper" },
        }}
      />,
    );
    await act(async () => resolve(response({ ok: true, preview })));
    expect(screen.getByText("Second paper")).toBeVisible();
    expect(screen.queryByLabelText(t("abstractText"))).not.toBeInTheDocument();
  });
  it("keeps empty/PDF-only paths honest without asking for JSON or a new abstract file", () => {
    renderComposer({ artifacts: [{ ...artifact, path: "paper.pdf" }] });
    expect(screen.getByRole("status")).toHaveTextContent(t("abstractNoText"));
    expect(
      screen.queryByRole("button", { name: t("abstractReadText") }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeEnabled();
  });
  it("displays preview rejection without revealing stale text or enabling creation", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        response(
          { ok: false, code: "stale_input", error: "Selected source changed" },
          400,
        ),
      ),
    );
    renderComposer();
    const user = userEvent.setup();
    await user.selectOptions(
      screen.getByLabelText(t("abstractChooseFile")),
      artifact.id,
    );
    await user.click(
      screen.getByRole("button", { name: t("abstractReadText") }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Selected source changed",
    );
    expect(screen.queryByLabelText(t("abstractText"))).not.toBeInTheDocument();
  });
});

describe("safe profile review and unavailable runner", () => {
  it("shows saved source and candidate as text, not semantic acceptance or executable HTML", () => {
    const goBack = vi.fn();
    const { container } = render(
      <AbstractDraftReview
        task={{
          ...task,
          status: "awaiting_human",
          result: { prose: "<img src=x onerror=alert(1)> candidate" },
        }}
        t={t}
        onReturnToSource={goBack}
      />,
    );
    expect(
      screen.getByText("<img src=x onerror=alert(1)> candidate"),
    ).toBeVisible();
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText(t("abstractBindingNote"))).toBeVisible();
    expect(screen.getByText("😀 Abstract: A.")).toBeVisible();
    fireEvent.click(
      screen.getByRole("button", { name: t("abstractReturnSource") }),
    );
    expect(goBack).toHaveBeenCalledWith(source.id);
  });
  it("disables Run without a known available runner and hides only incompatible profile import", () => {
    render(
      <TaskCard
        task={task}
        t={t}
        approvalMessage="Unavailable"
        onSaved={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /Run/ })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent(
      t("abstractRunnerUnavailable"),
    );
    expect(screen.queryByText(t("importResult"))).not.toBeInTheDocument();
  });
  it("retains existing prose import for ordinary tasks", () => {
    render(
      <TaskCard
        task={{ ...task, operation: "frame" }}
        t={t}
        approvalMessage="Unavailable"
        onSaved={vi.fn()}
      />,
    );
    expect(screen.getByText(t("importResult"))).toBeVisible();
  });
});

const project = {
  id: "river",
  title: "River project",
  archetype: "review" as const,
  goal: "Compare sources",
};
const workspace: Workspace = {
  ok: true,
  projects: [project],
  capabilities: {
    codex: { status: "unavailable", message: "Unavailable" },
    writing: { status: "unavailable", message: "Unavailable" },
    approval: { status: "unavailable", message: "Unavailable" },
  },
  protection_scope: "Local only",
};
const detail: ProjectDetail = {
  ok: true,
  project,
  records: [source],
  artifacts: [artifact],
  tasks: [],
  actions: [],
  manuscript: null,
  workflow: null,
  warnings: [],
};

describe("source to prepared task to same-source return", () => {
  it("navigates to exact task and back to its source without internal-ID entry or model calls", async () => {
    let tasks: Task[] = [];
    const fetch = vi.fn(
      async (input: RequestInfo | URL, options?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/workspace")) return response(workspace);
        if (url.endsWith("/text")) return response({ ok: true, preview });
        if (url.endsWith("/tasks") && options?.method === "POST") {
          tasks = [task];
          return response({ ok: true, task });
        }
        return response({ ...detail, tasks });
      },
    );
    vi.stubGlobal("fetch", fetch);
    window.history.replaceState({}, "", "#literature");
    const user = userEvent.setup();
    render(<App />);
    await user.click(
      await screen.findByRole("button", { name: t("abstractOpen") }),
    );
    const textarea = await readPreview();
    selectPassage(textarea);
    expect(
      screen.getByRole("button", { name: t("abstractPrepare") }),
    ).toBeEnabled();
    await user.click(
      screen.getByRole("button", { name: t("abstractPrepare") }),
    );
    await waitFor(() =>
      expect(document.getElementById(`review-task-${task.id}`)).toHaveFocus(),
    );
    expect(screen.getByRole("button", { name: /Run/ })).toBeDisabled();
    // Composition: the overview opens this exact new operation, and its
    // source return still works after the overview/review round trip.
    await user.click(screen.getByRole("button", { name: t("returnOverview") }));
    expect(window.location.hash).toBe("#overview");
    await user.click(
      screen.getByRole("button", { name: `Open task ${task.id}` }),
    );
    await waitFor(() =>
      expect(document.getElementById(`review-task-${task.id}`)).toHaveFocus(),
    );
    await user.click(
      screen.getByRole("button", { name: t("abstractReturnSource") }),
    );
    await waitFor(() =>
      expect(document.getElementById(`record-${source.id}`)).toHaveFocus(),
    );
    expect(screen.getByLabelText(t("abstractText"))).toHaveValue(
      "Title\n😀 Abstract: A.\nEnd",
    );
    expect(
      fetch.mock.calls.filter((call) => call[1]?.method === "POST"),
    ).toHaveLength(1);
    expect(
      fetch.mock.calls.some((call) => String(call[0]).includes("/run")),
    ).toBe(false);
  }, 10000);
});

describe("preparation interruption and explicit execution", () => {
  it("does not duplicate an in-flight preparation and disables cancellation until its outcome", async () => {
    let resolve!: (value: Response) => void;
    const fetch = vi.fn((input: RequestInfo | URL, options?: RequestInit) =>
      options?.method === "POST"
        ? new Promise<Response>((done) => {
            resolve = done;
          })
        : Promise.resolve(response({ ok: true, preview })),
    );
    vi.stubGlobal("fetch", fetch);
    const prepared = vi.fn();
    renderComposer({ onPrepared: prepared });
    selectPassage(await readPreview());
    const button = screen.getByRole("button", { name: t("abstractPrepare") });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(
      fetch.mock.calls.filter((call) => call[1]?.method === "POST"),
    ).toHaveLength(1);
    await act(async () => resolve(response({ ok: true, task })));
    expect(prepared).toHaveBeenCalledTimes(1);
  });
  it("keeps selected text and purpose after a rejected prepare without automatic replay", async () => {
    const fetch = vi.fn(
      async (input: RequestInfo | URL, options?: RequestInit) =>
        options?.method === "POST"
          ? response(
              {
                ok: false,
                error: "Selected source changed",
                code: "stale_input",
              },
              400,
            )
          : response({ ok: true, preview }),
    );
    vi.stubGlobal("fetch", fetch);
    renderComposer();
    selectPassage(await readPreview());
    const user = userEvent.setup();
    await user.type(
      screen.getByLabelText(t("abstractPurpose")),
      "Compare uncertainty",
    );
    await user.click(
      screen.getByRole("button", { name: t("abstractPrepare") }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Selected source changed",
    );
    expect(screen.getByLabelText(t("abstractPurpose"))).toHaveValue(
      "Compare uncertainty",
    );
    expect(screen.getByLabelText(t("abstractText"))).toBeVisible();
    expect(
      fetch.mock.calls.filter((call) => call[1]?.method === "POST"),
    ).toHaveLength(1);
  });
  it("never runs automatically but dispatches one explicit Run when runner is reported available", async () => {
    const fetch = vi.fn(
      async (_input: RequestInfo | URL, _options?: RequestInit) =>
        response({ ok: true, task: { ...task, status: "running" } }),
    );
    vi.stubGlobal("fetch", fetch);
    const saved = vi.fn();
    render(
      <TaskCard
        task={task}
        runnerAvailable
        t={t}
        approvalMessage="Unavailable"
        onSaved={saved}
      />,
    );
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.getByText(t("abstractCostUnknown"))).toBeVisible();
    await userEvent.setup().click(screen.getByRole("button", { name: /Run/ }));
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(String(fetch.mock.calls[0][0])).toBe(`/api/v1/tasks/${task.id}/run`);
    expect(saved).toHaveBeenCalled();
  });
  it("cancel returns focus to the original source without a mutation", async () => {
    const fetch = vi.fn(async (input: RequestInfo | URL) =>
      response(String(input).endsWith("/workspace") ? workspace : detail),
    );
    vi.stubGlobal("fetch", fetch);
    window.history.replaceState({}, "", "#literature");
    const user = userEvent.setup();
    render(<App />);
    await user.click(
      await screen.findByRole("button", { name: t("abstractOpen") }),
    );
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() =>
      expect(document.getElementById(`record-${source.id}`)).toHaveFocus(),
    );
    expect(
      screen.queryByLabelText(t("abstractChooseFile")),
    ).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});

describe("superseding source navigation", () => {
  it("does not mistake a newer supported-page navigation for a removed source", async () => {
    const frames = new Map<number, FrameRequestCallback>();
    let id = 0;
    vi.stubGlobal("requestAnimationFrame", (fn: FrameRequestCallback) => {
      frames.set(++id, fn);
      return id;
    });
    vi.stubGlobal("cancelAnimationFrame", (key: number) => frames.delete(key));
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) =>
        response(
          String(input).endsWith("/workspace")
            ? workspace
            : { ...detail, tasks: [task] },
        ),
      ),
    );
    window.history.replaceState({}, "", "#review");
    render(<App />);
    const back = await screen.findByRole("button", {
      name: t("abstractReturnSource"),
    });
    fireEvent.click(back);
    act(() => {
      window.history.replaceState({}, "", "#review");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    act(() => {
      const callbacks = [...frames.values()];
      frames.clear();
      callbacks.forEach((fn) => fn(0));
    });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Review",
    );
    expect(screen.getByRole("heading", { level: 1 })).toHaveFocus();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("uncertain write outcomes are not replayed", () => {
  it.each(["network", "unreadable", "server"])(
    "keeps unknown preparation (%s) scoped and offers existing review, not blind new-task submission",
    async (kind) => {
      const fetch = vi.fn(
        async (input: RequestInfo | URL, options?: RequestInit) => {
          if (options?.method !== "POST")
            return response({ ok: true, preview });
          if (kind === "network") throw new TypeError("Connection interrupted");
          if (kind === "unreadable")
            return new Response("not json", { status: 200 });
          return response({ ok: false, error: "Server unavailable" }, 503);
        },
      );
      vi.stubGlobal("fetch", fetch);
      const review = vi.fn();
      renderComposer({ onReview: review });
      selectPassage(await readPreview());
      await userEvent
        .setup()
        .click(screen.getByRole("button", { name: t("abstractPrepare") }));
      expect(
        await screen.findByText(t("abstractPrepareUncertain")),
      ).toBeVisible();
      expect(screen.queryByText(t("errorHelp"))).not.toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: t("abstractPrepare") }),
      ).toBeDisabled();
      expect(screen.getByLabelText(t("abstractChooseFile"))).toBeDisabled();
      await userEvent
        .setup()
        .click(
          screen.getByRole("button", { name: t("abstractReviewExisting") }),
        );
      expect(review).toHaveBeenCalledWith(undefined);
      expect(
        fetch.mock.calls.filter((call) => call[1]?.method === "POST"),
      ).toHaveLength(1);
    },
  );
  it("retains the known task on uncertain Run and unlocks only after an updated task read", async () => {
    const fetch = vi.fn(
      async (_input: RequestInfo | URL, _options?: RequestInit) => {
        throw new TypeError("Connection interrupted");
      },
    );
    vi.stubGlobal("fetch", fetch);
    const props = {
      task,
      runnerAvailable: true,
      t,
      approvalMessage: "Unavailable",
      onSaved: vi.fn(),
    };
    const view = render(<TaskCard {...props} />);
    const run = screen.getByRole("button", { name: /Run/ });
    fireEvent.click(run);
    fireEvent.click(run);
    expect(await screen.findByText(t("abstractRunUncertain"))).toBeVisible();
    expect(screen.queryByText(t("errorHelp"))).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Run/ })).toBeDisabled();
    expect(screen.getByText("😀 Abstract: A.")).toBeVisible();
    expect(fetch).toHaveBeenCalledTimes(1);
    view.rerender(<TaskCard {...props} />);
    expect(screen.getByRole("button", { name: /Run/ })).toBeDisabled();
    view.rerender(<TaskCard {...props} task={{ ...task }} />);
    expect(screen.getByRole("button", { name: /Run/ })).toBeDisabled();
    expect(screen.getByText(t("abstractRunUncertain"))).toBeVisible();
    view.rerender(
      <TaskCard
        {...props}
        task={{
          ...task,
          status: "running",
          updated_at: "2026-10-24T02:00:00Z",
        }}
      />,
    );
    expect(
      screen.queryByText(t("abstractRunUncertain")),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Run task/ }),
    ).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});

describe("source changes during post-save refresh", () => {
  it("keeps the saved task id but does not navigate an unmounted source after refresh completes", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: RequestInfo | URL, options?: RequestInit) =>
        response(
          options?.method === "POST"
            ? { ok: true, task }
            : { ok: true, preview },
        ),
      ),
    );
    let release!: () => void;
    const onPrepared = vi.fn(
      () =>
        new Promise<void>((done) => {
          release = done;
        }),
    );
    const onReview = vi.fn();
    const props = {
      projectId: "river",
      source,
      artifacts: [artifact],
      capability: { status: "unavailable", message: "" },
      t,
      onPrepared,
      onReview,
      onCancel: vi.fn(),
    };
    const view = render(<AbstractDraftComposer key="a" {...props} />);
    selectPassage(await readPreview());
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: t("abstractPrepare") }));
    await waitFor(() => expect(onPrepared).toHaveBeenCalledWith(task));
    view.rerender(
      <AbstractDraftComposer
        key="b"
        {...props}
        projectId="other-project"
        source={{
          ...source,
          id: "other-source",
          data: { ...source.data, title: "Other source" },
        }}
      />,
    );
    await act(async () => release());
    expect(onReview).not.toHaveBeenCalled();
    expect(screen.getByText("Other source")).toBeVisible();
    expect(screen.queryByLabelText(t("abstractText"))).not.toBeInTheDocument();
  });
});

describe("newer page navigation wins over late preparation", () => {
  it("keeps Manuscript open after pending Prepare finishes, while retaining the known task for explicit return", async () => {
    let tasks: Task[] = [];
    let complete!: (value: Response) => void;
    const fetch = vi.fn((input: RequestInfo | URL, options?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/workspace"))
        return Promise.resolve(response(workspace));
      if (url.endsWith("/text"))
        return Promise.resolve(response({ ok: true, preview }));
      if (options?.method === "POST")
        return new Promise<Response>((resolve) => {
          complete = resolve;
        });
      return Promise.resolve(response({ ...detail, tasks }));
    });
    vi.stubGlobal("fetch", fetch);
    window.history.replaceState({}, "", "#literature");
    const user = userEvent.setup();
    render(<App />);
    await user.click(
      await screen.findByRole("button", { name: t("abstractOpen") }),
    );
    selectPassage(await readPreview());
    await user.click(
      screen.getByRole("button", { name: t("abstractPrepare") }),
    );
    await user.click(screen.getByRole("link", { name: /Manuscript/ }));
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
        "Manuscript",
      ),
    );
    tasks = [task];
    await act(async () => complete(response({ ok: true, task })));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(6));
    expect(window.location.hash).toBe("#manuscript");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Manuscript",
    );
    expect(
      fetch.mock.calls.filter((call) => call[1]?.method === "POST"),
    ).toHaveLength(1);
    await user.click(screen.getByRole("link", { name: /Literature/ }));
    await user.click(
      await screen.findByRole("button", { name: t("abstractOpenPrepared") }),
    );
    await waitFor(() =>
      expect(document.getElementById(`review-task-${task.id}`)).toHaveFocus(),
    );
  }, 10000);
});

it("independent full App preserves uncertain Run through failed Refresh and same-state Retry", async () => {
  let failNextProjectRead = false;
  let projectReads = 0;
  const fetch = vi.fn(
    async (input: RequestInfo | URL, options?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/run") && options?.method === "POST")
        throw new TypeError("Synthetic unknown Run outcome");
      if (url.endsWith("/workspace"))
        return response({
          ...workspace,
          capabilities: {
            ...workspace.capabilities,
            codex: { status: "available", message: "Synthetic runner" },
          },
        });
      if (url.endsWith("/projects/river")) {
        projectReads += 1;
        if (failNextProjectRead) {
          failNextProjectRead = false;
          return response(
            { ok: false, error: "Synthetic refresh failure" },
            503,
          );
        }
        return response({ ...detail, tasks: [task] });
      }
      throw new Error(`Unexpected test request ${url}`);
    },
  );
  vi.stubGlobal("fetch", fetch);
  window.history.replaceState({}, "", "#review");
  const user = userEvent.setup();
  render(<App />);
  await user.click(
    await screen.findByRole("button", { name: /Run connected task/ }),
  );
  expect(await screen.findByText(t("abstractRunUncertain"))).toBeVisible();
  expect(
    screen.getByRole("button", { name: /Run connected task/ }),
  ).toBeDisabled();
  failNextProjectRead = true;
  await user.click(screen.getByRole("button", { name: "Refresh" }));
  expect(await screen.findByText("Synthetic refresh failure")).toBeVisible();
  expect(
    screen.getByRole("button", { name: /Run connected task/ }),
  ).toBeDisabled();
  expect(screen.getByText(t("refreshRetained"))).toBeVisible();
  await user.click(screen.getByRole("button", { name: t("retry") }));
  const runAfterRetry = await screen.findByRole("button", {
    name: /Run connected task/,
  });
  await waitFor(() => expect(projectReads).toBe(3));
  expect(
    fetch.mock.calls.filter((call) => String(call[0]).endsWith("/run")),
  ).toHaveLength(1);
  expect(runAfterRetry).toBeDisabled();
}, 10000);

describe("transient refresh failure preserves source inputs and uncertainty", () => {
  it.each(["workspace", "project"])(
    "retains uncertain Prepare through failed %s read and Retry without replay",
    async (failure) => {
      let failNext = false;
      const fetch = vi.fn(
        async (input: RequestInfo | URL, options?: RequestInit) => {
          const url = String(input);
          if (options?.method === "POST")
            throw new TypeError("Synthetic unknown Prepare outcome");
          if (url.endsWith("/text")) return response({ ok: true, preview });
          if (
            failNext &&
            url.endsWith(
              failure === "workspace" ? "/workspace" : "/projects/river",
            )
          ) {
            failNext = false;
            return response(
              { ok: false, error: "Synthetic refresh failure" },
              503,
            );
          }
          return response(url.endsWith("/workspace") ? workspace : detail);
        },
      );
      vi.stubGlobal("fetch", fetch);
      window.history.replaceState({}, "", "#literature");
      const user = userEvent.setup();
      render(<App />);
      await user.click(
        await screen.findByRole("button", { name: t("abstractOpen") }),
      );
      selectPassage(await readPreview());
      await user.type(
        screen.getByLabelText(t("abstractPurpose")),
        "Retain this synthetic purpose",
      );
      await user.click(
        screen.getByRole("button", { name: t("abstractPrepare") }),
      );
      expect(
        await screen.findByText(t("abstractPrepareUncertain")),
      ).toBeVisible();
      failNext = true;
      await user.click(screen.getByRole("button", { name: "Refresh" }));
      expect(
        await screen.findByText("Synthetic refresh failure"),
      ).toBeVisible();
      expect(screen.getByText(t("refreshRetained"))).toBeVisible();
      const text = screen.getByLabelText(t("abstractText"));
      expect(text).toHaveValue("Title\n😀 Abstract: A.\nEnd");
      expect(screen.getByLabelText(t("abstractPurpose"))).toHaveValue(
        "Retain this synthetic purpose",
      );
      expect(
        screen.getByRole("button", { name: t("abstractPrepare") }),
      ).toBeDisabled();
      await user.click(screen.getByRole("button", { name: t("retry") }));
      await waitFor(() =>
        expect(
          screen.queryByText("Synthetic refresh failure"),
        ).not.toBeInTheDocument(),
      );
      expect(screen.getByLabelText(t("abstractText"))).toBe(text);
      expect(screen.getByText(t("abstractPrepareUncertain"))).toBeVisible();
      expect(
        screen.getByRole("button", { name: t("abstractPrepare") }),
      ).toBeDisabled();
      expect(screen.getByLabelText(t("abstractPurpose"))).toHaveValue(
        "Retain this synthetic purpose",
      );
      expect(
        fetch.mock.calls.filter((call) => call[1]?.method === "POST"),
      ).toHaveLength(1);
    },
    10000,
  );
});

it("explicit saved-copy reopen preserves keyless Prepare uncertainty and does not reset on ordinary rerender", async () => {
  const other = {
    ...artifact,
    id: "other-evidence",
    path: "evidence/other.txt",
  };
  const otherPreview = {
    ...preview,
    artifact_id: other.id,
    path: other.path,
    text: "Other selected text",
  };
  const fetch = vi.fn(
    async (_input: RequestInfo | URL, options?: RequestInit) => {
      if (options?.method === "POST")
        throw new TypeError("Synthetic lost Prepare reply");
      return response({ ok: true, preview: otherPreview });
    },
  );
  vi.stubGlobal("fetch", fetch);
  const props = {
    projectId: "river",
    source,
    artifacts: [artifact, other],
    capability: { status: "unavailable", message: "Unavailable" },
    t,
    onPrepared: vi.fn(),
    onCancel: vi.fn(),
    initialArtifactId: artifact.id,
    initialPreview: preview,
  };
  const { rerender } = render(
    <AbstractDraftComposer {...props} restoreVersion={0} />,
  );
  const user = userEvent.setup();
  await user.selectOptions(
    screen.getByLabelText(t("abstractChooseFile")),
    other.id,
  );
  await user.click(screen.getByRole("button", { name: t("abstractReadText") }));
  await screen.findByLabelText(t("abstractText"));
  rerender(
    <AbstractDraftComposer
      {...props}
      artifacts={[...props.artifacts]}
      restoreVersion={0}
    />,
  );
  expect(screen.getByLabelText(t("abstractChooseFile"))).toHaveValue(other.id);
  await user.click(
    screen.getByRole("button", { name: t("abstractSelectEntire") }),
  );
  await user.click(screen.getByRole("button", { name: t("abstractPrepare") }));
  await screen.findByText(t("abstractPrepareUncertain"));
  rerender(
    <AbstractDraftComposer
      {...props}
      restoreVersion={1}
      separateIntentVersion={1}
    />,
  );
  expect(screen.getByText(t("abstractRestoreBlocked"))).toBeVisible();
  expect(screen.getByLabelText(t("abstractChooseFile"))).toHaveValue(other.id);
  expect(screen.getByLabelText(t("abstractText"))).toHaveValue(
    otherPreview.text,
  );
  expect(
    screen.getByRole("button", { name: t("abstractPrepare") }),
  ).toBeDisabled();
  expect(
    fetch.mock.calls.filter((call) => call[1]?.method === "POST"),
  ).toHaveLength(1);
});

// Actual DOM check paired with the Python smoke/i18n binding regression.
// No browser launch or out-of-root Vite module access is required.
it("browser smoke read-source locator matches the rendered explicit action", async () => {
  const fetch = vi.fn(async (_input: RequestInfo | URL, _options?: RequestInit) => response({ ok: true, preview }));
  vi.stubGlobal("fetch", fetch);
  renderComposer();
  const user = userEvent.setup();
  await user.selectOptions(screen.getByLabelText(t("abstractChooseFile")), artifact.id);
  expect(fetch).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Read selected saved text" }));
  expect(await screen.findByLabelText(t("abstractText"))).toHaveValue(preview.text.replace(/\r\n?/g, "\n"));
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(String(fetch.mock.calls[0][0])).toBe("/api/v1/projects/river/artifacts/evidence-a/text");
  expect(fetch.mock.calls[0][1]?.method ?? "GET").toBe("GET");

});
