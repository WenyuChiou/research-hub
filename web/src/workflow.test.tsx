import { describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { MutationForm } from "./components";
import {
  dictionaries,
  en,
  nextOperation,
  statusLabel,
  statusTone,
  translator,
} from "./i18n";
import { parseOutputArtifacts, TaskCard } from "./Tasks";
import type { ProjectDetail, Task, Workspace } from "./types";

const t = translator("en");
const project = {
  id: "river-study",
  title: "River adaptation",
  archetype: "empirical" as const,
  goal: "Understand adaptation choices.",
};
const workspace: Workspace = {
  ok: true,
  projects: [project],
  capabilities: {
    codex: { status: "unavailable", message: "Connect Codex locally." },
    writing: { status: "ready", message: "Writing support ready." },
    approval: {
      status: "unavailable",
      message:
        "research-hub task decide <task-id> --root <workspace> --outcome accept --actor <name> --rationale <reason>",
    },
  },
  protection_scope: "Selected workspace files only.",
};
const detail: ProjectDetail = {
  ok: true,
  project,
  records: [],
  tasks: [],
  actions: [],
  artifacts: [],
  manuscript: null,
  workflow: null,
  warnings: [],
};
const task: Task = {
  id: "task-1",
  operation: "frame",
  mode: "handoff",
  status: "awaiting_agent",
  action_hash: "a".repeat(64),
};
const response = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });

describe("locale and workflow semantics", () => {
  it("provides nonempty matching English and Traditional Chinese messages", () => {
    expect(Object.keys(dictionaries["zh-TW"]).sort()).toEqual(
      Object.keys(en).sort(),
    );
    expect(
      Object.values(dictionaries["zh-TW"]).every((value) => value.trim()),
    ).toBe(true);
  });
  it("distinguishes pending human review from human acceptance", () => {
    expect(statusLabel("awaiting_human", t)).toBe("Awaiting human review");
    expect(statusLabel("completed", t)).toBe("Accepted by human");
    expect(statusTone("awaiting_human")).toBe("warn");
    expect(statusTone("completed")).toBe("good");
    expect(statusTone("failed")).toBe("danger");
    expect(statusLabel("future_server_state", t)).toBe("future_server_state");
  });
  it("chooses the next operation from recorded research state", () => {
    expect(nextOperation(detail).operation).toBe("frame");
    const framed = {
      ...detail,
      records: [{ id: "q", kind: "question", data: { text: "Why?" } }],
    };
    expect(nextOperation(framed).operation).toBe("synthesize");
    const claims = {
      ...framed,
      records: [
        ...framed.records,
        { id: "c", kind: "claim", data: { text: "Claim" } },
      ],
    };
    expect(nextOperation(claims).operation).toBe("outline");
    const outlined = {
      ...claims,
      records: [
        ...claims.records,
        { id: "o", kind: "outline", data: { text: "Outline" } },
      ],
    };
    expect(nextOperation(outlined).operation).toBe("draft");
    expect(
      nextOperation({
        ...outlined,
        artifacts: [
          {
            id: "m",
            path: "paper.md",
            role: "main_manuscript",
            sha256: "a".repeat(64),
            current: true,
          },
        ],
      }).operation,
    ).toBe("review");
  });
  it("validates imported artifact fingerprints", () => {
    expect(parseOutputArtifacts(`paper.md | ${"a".repeat(64)}`)).toEqual([
      { path: "paper.md", sha256: "a".repeat(64) },
    ]);
    expect(parseOutputArtifacts("")).toEqual([]);
    expect(() => parseOutputArtifacts("paper.md")).toThrow();
    expect(() => parseOutputArtifacts("paper.md | bad-sha")).toThrow();
  });
});

describe("researcher interactions", () => {
  it("preserves form entries after a failed request", async () => {
    const user = userEvent.setup();
    render(
      <MutationForm
        t={t}
        submit="Record question"
        fields={[{ name: "text", label: "Question" }]}
        onSubmit={async () => {
          throw new Error("Workspace is read-only");
        }}
      />,
    );
    await user.type(
      screen.getByLabelText(/Question/),
      "What changes after drought?",
    );
    await user.click(screen.getByRole("button", { name: /Record question/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Workspace is read-only",
    );
    expect(screen.getByLabelText(/Question/)).toHaveValue(
      "What changes after drought?",
    );
  });
  it("shows six pages, switches locale, and records a research question", async () => {
    const user = userEvent.setup();
    let current = structuredClone(detail);
    const fetch = vi
      .fn()
      .mockImplementation(async (url: string, options: RequestInit) => {
        if (url === "/api/v1/workspace") return response(workspace);
        if (url.endsWith("/records")) {
          const record = JSON.parse(String(options.body));
          current = { ...current, records: [{ id: "q1", ...record }] };
          return response({ ok: true });
        }
        return response(current);
      });
    vi.stubGlobal("fetch", fetch);
    render(<App />);
    expect(
      await screen.findByText("Understand adaptation choices."),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("navigation")).getAllByRole("link"),
    ).toHaveLength(6);
    await user.click(
      screen.getByText("Record question", { selector: "summary" }),
    );
    await user.type(
      screen.getByRole("textbox", { name: /^Question/ }),
      "How do choices change?",
    );
    await user.click(screen.getByRole("button", { name: /^Record question/ }));
    expect(
      await screen.findByText("How do choices change?", { selector: "p" }),
    ).toBeInTheDocument();
    expect(
      fetch.mock.calls.some(
        ([url, options]) =>
          url.endsWith("/records") &&
          JSON.parse(options.body).data.text === "How do choices change?",
      ),
    ).toBe(true);
    await user.click(screen.getByRole("button", { name: "繁體中文" }));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "研究總覽",
    );
    expect(document.documentElement.lang).toBe("zh-TW");
  });
  it("prepares a handoff task without automatically starting an agent", async () => {
    const user = userEvent.setup();
    let prepared = false;
    const fetch = vi
      .fn()
      .mockImplementation(async (url: string, options: RequestInit) => {
        if (url === "/api/v1/workspace") return response(workspace);
        if (url.endsWith("/tasks") && options.method === "POST") {
          prepared = true;
          return response({ ok: true, task });
        }
        return response({ ...detail, tasks: prepared ? [task] : [] });
      });
    vi.stubGlobal("fetch", fetch);
    render(<App />);
    await screen.findByText("Understand adaptation choices.");
    await user.click(screen.getByRole("link", { name: /^Review & delivery/ }));
    await user.type(
      screen.getByLabelText(/Instructions and acceptance criteria/),
      "Define scope and evidence needed.",
    );
    await user.click(screen.getByRole("button", { name: /^Prepare task/ }));
    expect(
      await screen.findByRole("button", { name: /Download handoff packet/ }),
    ).toBeInTheDocument();
    const post = fetch.mock.calls.find(
      ([url, options]) => url.endsWith("/tasks") && options.method === "POST",
    );
    expect(JSON.parse(post![1].body)).toEqual({
      operation: "frame",
      mode: "handoff",
      instructions: "Define scope and evidence needed.",
    });
    expect(fetch.mock.calls.some(([url]) => url.endsWith("/run"))).toBe(false);
  });
  it("shows the CLI approval instruction when no human session is present", () => {
    render(
      <TaskCard
        task={{
          ...task,
          status: "awaiting_human",
          result: { prose: "Candidate work" },
        }}
        approvalMessage={workspace.capabilities.approval.message}
        t={t}
        onSaved={async () => {}}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Record decision" }),
    ).toBeDisabled();
    expect(
      screen.getByText(workspace.capabilities.approval.message),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("option", { name: "Accept" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Run connected task/ }),
    ).not.toBeInTheDocument();
  });
  it("imports host output for review without posting acceptance", async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn().mockResolvedValue(undefined);
    const fetch = vi
      .fn()
      .mockResolvedValue(
        response({ ok: true, task: { ...task, status: "awaiting_human" } }),
      );
    vi.stubGlobal("fetch", fetch);
    render(
      <TaskCard
        task={task}
        approvalMessage="CLI instruction"
        t={t}
        onSaved={onSaved}
      />,
    );
    await user.click(
      screen.getByText("Import host output", { selector: "summary" }),
    );
    expect(
      screen.getByLabelText(/Input fingerprint from the handoff packet/),
    ).toHaveValue("");
    await user.type(
      screen.getByLabelText(/Input fingerprint from the handoff packet/),
      "b".repeat(64),
    );
    await user.type(
      screen.getByLabelText(/Agent output/),
      "Candidate findings with limitations.",
    );
    await user.click(
      screen.getByRole("button", { name: /Import for human review/ }),
    );
    await waitFor(() =>
      expect(onSaved).toHaveBeenCalledWith("Output imported for human review."),
    );
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/tasks/task-1/result");
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
      input_hash: "b".repeat(64),
      prose: "Candidate findings with limitations.",
      status: "completed",
      artifacts: [],
    });
  });
  it("does not offer implicit retries from failed or blocked tasks", () => {
    const { rerender } = render(
      <TaskCard
        task={{ ...task, mode: "connected", status: "failed" }}
        approvalMessage="CLI"
        t={t}
        onSaved={async () => {}}
      />,
    );
    expect(
      screen.queryByRole("button", { name: /Run connected task/ }),
    ).not.toBeInTheDocument();
    rerender(
      <TaskCard
        task={{ ...task, mode: "connected", status: "blocked" }}
        approvalMessage="CLI"
        t={t}
        onSaved={async () => {}}
      />,
    );
    expect(
      screen.queryByRole("button", { name: /Run connected task/ }),
    ).not.toBeInTheDocument();
  });
  it("polls running tasks at three seconds and stops after the transition to human review", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    let transitioned = false;
    const fetch = vi.fn().mockImplementation(async (url: string) => {
      if (url === "/api/v1/workspace") return response(workspace);
      if (url === "/api/v1/tasks/task-1") {
        transitioned = true;
        return response({
          ok: true,
          task: { ...task, status: "awaiting_human" },
        });
      }
      return response({
        ...detail,
        tasks: [
          {
            ...task,
            mode: "connected",
            status: transitioned ? "awaiting_human" : "running",
          },
        ],
      });
    });
    vi.stubGlobal("fetch", fetch);
    try {
      let unmount = () => {};
      await act(async () => {
        unmount = render(<App />).unmount;
      });
      expect(
        fetch.mock.calls.filter(([url]) => url === "/api/v1/tasks/task-1"),
      ).toHaveLength(0);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });
      expect(
        fetch.mock.calls.filter(([url]) => url === "/api/v1/tasks/task-1"),
      ).toHaveLength(1);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(9000);
      });
      expect(
        fetch.mock.calls.filter(([url]) => url === "/api/v1/tasks/task-1"),
      ).toHaveLength(1);
      unmount();
    } finally {
      vi.clearAllTimers();
      vi.useRealTimers();
    }
  });
});
