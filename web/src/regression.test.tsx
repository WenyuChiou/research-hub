import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { ProjectPages } from "./Pages";
import { TaskCard } from "./Tasks";
import { translator } from "./i18n";
import type { Locale, ProjectDetail, Task, Workspace } from "./types";

const t = translator("en");
const hash = "a".repeat(64);
const task: Task = {
  id: "task-pending",
  operation: "outline",
  mode: "handoff",
  status: "awaiting_human",
  action_hash: hash,
};
const detail: ProjectDetail = {
  ok: true,
  project: {
    id: "study",
    title: "Study",
    archetype: "empirical",
    goal: "Investigate evidence.",
  },
  records: [],
  artifacts: [],
  tasks: [],
  actions: [],
  manuscript: null,
  workflow: null,
  warnings: [],
};
const workspace: Workspace = {
  ok: true,
  projects: [detail.project],
  capabilities: {
    codex: { status: "unavailable", message: "No connected agent." },
    writing: { status: "available", message: "Writing adapter available." },
    approval: { status: "unavailable", message: "Use the interactive CLI." },
  },
  protection_scope: "Selected workspace.",
};
const response = (value: unknown) =>
  new Response(JSON.stringify(value), {
    headers: { "Content-Type": "application/json" },
  });

describe("final workspace regressions", () => {
  it.each<Locale>(["en", "zh-TW"])("shows persisted failure diagnostics in %s", (locale) => {
    const translate = translator(locale);
    render(<TaskCard task={{ ...task, status: "failed",
      error: "Executor event stream is invalid",
      execution_provenance: { stderr_log: ".research/tasks/task-pending/executions/run/stderr.txt" },
    }} t={translate} approvalMessage="CLI" onSaved={async () => {}} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Executor event stream is invalid");
    expect(screen.getByText(translate("taskDiagnostics"))).toBeInTheDocument();
    expect(screen.getByText(/executions\/run\/stderr.txt/)).toBeInTheDocument();
    expect(screen.queryByText(translate("noOutput"))).not.toBeInTheDocument();
  });
  it("clears a translated action notice only when the locale actually changes", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockImplementation(async (url: string) =>
          response(
            url.endsWith("/workspace")
              ? workspace
              : url.endsWith("/records")
                ? { ok: true }
                : detail,
          ),
        ),
    );
    render(<App />);
    await screen.findByText("Investigate evidence.");
    await user.click(
      screen.getByText("Record question", { selector: "summary" }),
    );
    await user.type(
      screen.getByRole("textbox", { name: "Question" }),
      "Which mechanism explains the result?",
    );
    await user.click(screen.getByRole("button", { name: /Record question/ }));
    await screen.findByRole("button", { name: "Dismiss message" });
    await user.click(screen.getByRole("button", { name: "EN" }));
    expect(
      screen.getByRole("button", { name: "Dismiss message" }),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "繁體中文" }),
    );
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "研究總覽",
    );
    expect(
      screen.queryByRole("button", { name: "關閉訊息" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("Saved to this project."),
    ).not.toBeInTheDocument();
  });

  it.each<Locale>(["en", "zh-TW"])(
    "prioritizes pending human review over running work, literature search, and new tasks in %s",
    async (locale) => {
      const user = userEvent.setup();
      const translate = translator(locale);
      const navigate = vi.fn();
      const pendingDetail = {
        ...detail,
        records: [
          {
            id: "question",
            kind: "question",
            data: { text: "A research question" },
          },
        ],
        tasks: [
          { ...task, id: "task-running", status: "running" },
          { ...task, id: "task-blocked", status: "blocked" },
          task,
        ],
      };
      render(
        <ProjectPages
          detail={pendingDetail}
          workspace={workspace}
          page="overview"
          t={translate}
          navigate={navigate}
          onSaved={async () => {}}
        />,
      );
      expect(
        screen.getByRole("heading", {
          name: translate("awaiting_human"),
          level: 2,
        }),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: translate("viewLiterature") }),
      ).not.toBeInTheDocument();
      await user.click(
        screen.getByRole("button", { name: translate("viewReview") }),
      );
      expect(navigate).toHaveBeenCalledWith("review");
    },
  );

  it("records review severity using the S0–S4 contract", async () => {
    const user = userEvent.setup();
    const fetch = vi.fn().mockResolvedValue(response({ ok: true }));
    vi.stubGlobal("fetch", fetch);
    const onSaved = vi.fn().mockResolvedValue(undefined);
    render(
      <ProjectPages
        detail={detail}
        workspace={workspace}
        page="review"
        t={t}
        navigate={() => {}}
        onSaved={onSaved}
      />,
    );
    await user.click(
      screen.getByText("Record review comment", { selector: "summary" }),
    );
    const severity = screen.getByRole("combobox", {
      name: "Severity",
    });
    expect(
      within(severity)
        .getAllByRole("option")
        .map((option) => (option as HTMLOptionElement).value),
    ).toEqual(["S0", "S1", "S2", "S3", "S4"]);
    await user.selectOptions(severity, "S2");
    await user.type(
      screen.getByRole("textbox", { name: "Comment" }),
      "The uncertainty statement needs supporting evidence.",
    );
    await user.click(
      screen.getByRole("button", { name: /Record review comment/ }),
    );
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
      kind: "review",
      data: {
        comment: "The uncertainty statement needs supporting evidence.",
        severity: "S2",
        status: "OPEN",
      },
    });
  });

  it("allows explicit blocked-task output import while keeping a running task owned by its executor", async () => {
    const user = userEvent.setup();
    const fetch = vi.fn().mockResolvedValue(response({ ok: true }));
    vi.stubGlobal("fetch", fetch);
    const onSaved = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(
      <TaskCard
        task={{ ...task, status: "blocked" }}
        t={t}
        approvalMessage="CLI"
        onSaved={onSaved}
      />,
    );
    expect(
      screen.queryByRole("button", { name: "Run connected task" }),
    ).not.toBeInTheDocument();
    await user.click(
      screen.getByText("Import host output", { selector: "summary" }),
    );
    await user.type(
      screen.getByRole("textbox", {
        name: "Input fingerprint from the handoff packet",
      }),
      hash,
    );
    await user.type(
      screen.getByRole("textbox", { name: "Agent output" }),
      "Recovered bounded output with its original input fingerprint.",
    );
    await user.click(
      screen.getByRole("button", { name: /Import for human review/ }),
    );
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/tasks/task-pending/result");
    expect(JSON.parse(fetch.mock.calls[0][1].body).input_hash).toBe(hash);
    rerender(
      <TaskCard
        task={{ ...task, status: "running" }}
        t={t}
        approvalMessage="CLI"
        onSaved={onSaved}
      />,
    );
    expect(
      screen.queryByText("Import host output", { selector: "summary" }),
    ).not.toBeInTheDocument();
  });

  it("preserves server task ordering and places task review before local delivery", () => {
    const orderedTasks = [
      { ...task, id: "newest-task" },
      { ...task, id: "older-task", status: "declined" },
    ];
    render(
      <ProjectPages
        detail={{ ...detail, tasks: orderedTasks }}
        workspace={workspace}
        page="review"
        t={t}
        navigate={() => {}}
        onSaved={async () => {}}
      />,
    );
    const cards = screen.getAllByRole("article");
    expect(cards).toHaveLength(2);
    expect(cards[0]).toHaveTextContent("newest-task");
    expect(cards[1]).toHaveTextContent("older-task");
    const tasksHeading = screen.getByRole("heading", {
      name: "Task activity",
      level: 2,
    });
    const deliveryHeading = screen.getByRole("heading", {
      name: "Local proposal delivery",
      level: 2,
    });
    expect(
      tasksHeading.compareDocumentPosition(deliveryHeading) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });
});
