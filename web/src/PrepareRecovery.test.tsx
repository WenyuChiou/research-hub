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
import App from "./App";
import { translator } from "./i18n";
const t = translator("en");
const namespace = "11111111-1111-4111-8111-111111111111";
const key = "22222222-2222-4222-8222-222222222222";
const project = {
  id: "river",
  title: "Public river study",
  archetype: "review",
  goal: "Compare sources",
};
const source = {
  id: "source-a",
  kind: "source",
  data: { title: "Public paper", locator: "https://example.org/paper" },
};
const artifact = {
  id: "evidence-a",
  path: "evidence/public.txt",
  role: "evidence",
  sha256: "a".repeat(64),
  current: true,
};
const task = {
  id: "saved-task",
  project_id: project.id,
  operation: "paper-abstract-draft",
  mode: "connected",
  status: "ready",
  action_hash: "b".repeat(64),
};
const workspace = {
  ok: true,
  projects: [project],
  capabilities: {
    codex: { status: "unavailable", message: "Unavailable" },
    writing: { status: "unavailable", message: "Unavailable" },
    approval: { status: "unavailable", message: "Unavailable" },
    prepare_reconciliation: { version: 1, workspace_instance_id: namespace },
  },
  protection_scope: "Local only",
};
const detail = {
  ok: true,
  project,
  records: [source],
  artifacts: [artifact],
  tasks: [] as (typeof task)[],
  actions: [],
  manuscript: null,
  workflow: null,
  warnings: [],
};
const storageKey = `research-hub:prepare:v1:${encodeURIComponent(window.location.origin)}:${namespace}:${encodeURIComponent(project.id)}:${key}`;
const response = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
async function selectAndPrepare() {
  const user = userEvent.setup();
  await user.click(
    await screen.findByRole("button", { name: t("abstractOpen") }),
  );
  await user.selectOptions(
    screen.getByLabelText(t("abstractChooseFile")),
    artifact.id,
  );
  await user.click(screen.getByRole("button", { name: t("abstractReadText") }));
  const area = (await screen.findByLabelText(
    t("abstractText"),
  )) as HTMLTextAreaElement;
  act(() => {
    area.focus();
    area.setSelectionRange(0, 8);
    fireEvent.select(area);
  });
  await user.click(screen.getByRole("button", { name: t("abstractPrepare") }));
}
function serve() {
  let saved = false;
  const fetch = vi.fn(
    async (input: RequestInfo | URL, options?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/workspace")) return response(workspace);
      if (url.endsWith("/text"))
        return response({
          ok: true,
          preview: {
            artifact_id: artifact.id,
            path: artifact.path,
            sha256: artifact.sha256,
            text: "Abstract text",
            codepoint_length: 13,
            bytes_read: 13,
            truncated: false,
          },
        });
      if (url.includes("/preparations/"))
        return response({
          ok: true,
          preparation: { state: "found", key },
          task,
        });
      if (options?.method === "POST") {
        const pending = JSON.parse(
          window.localStorage.getItem(storageKey) ?? "null",
        );
        expect(pending).toEqual({
          version: 1,
          workspace_instance_id: namespace,
          project_id: project.id,
          key,
          state: "pending",
        });
        expect(JSON.parse(String(options.body)).prepare_request).toEqual({
          version: 1,
          workspace_instance_id: namespace,
          key,
        });
        saved = true;
        throw new TypeError("Reply lost after commit");
      }
      return response({ ...detail, tasks: saved ? [task] : [] });
    },
  );
  vi.stubGlobal("fetch", fetch);
  vi.spyOn(window.crypto, "randomUUID").mockReturnValue(key);
  return fetch;
}
describe("exact preparation recovery", () => {
  it("persists opaque identity before POST and resolves a lost response by one exact GET, not another write", async () => {
    const fetch = serve();
    window.history.replaceState({}, "", "#literature");
    render(<App />);
    await selectAndPrepare();
    await waitFor(() =>
      expect(
        fetch.mock.calls.filter((call) =>
          String(call[0]).includes("/preparations/"),
        ),
      ).toHaveLength(1),
    );
    expect(
      fetch.mock.calls.filter((call) => call[1]?.method === "POST"),
    ).toHaveLength(1);
    const lookup = fetch.mock.calls.find((call) =>
      String(call[0]).includes("/preparations/"),
    )!;
    expect(lookup[1]?.headers).toMatchObject({
      "X-Workspace-Instance": namespace,
    });
    await waitFor(() =>
      expect(document.getElementById(`review-task-${task.id}`)).toHaveFocus(),
    );
    expect(window.localStorage.getItem(storageKey)).toBeNull();
    expect(
      fetch.mock.calls.some((call) => String(call[0]).endsWith("/run")),
    ).toBe(false);
  }, 10000);
  it("recovers an existing pending key on reload without reconstructing a payload or POSTing", async () => {
    window.localStorage.setItem(
      storageKey,
      JSON.stringify({
        version: 1,
        workspace_instance_id: namespace,
        project_id: project.id,
        key,
        state: "pending",
      }),
    );
    const fetch = serve();
    render(<App />);
    await waitFor(() =>
      expect(
        fetch.mock.calls.filter((call) =>
          String(call[0]).includes("/preparations/"),
        ),
      ).toHaveLength(1),
    );
    expect(
      fetch.mock.calls.filter((call) => call[1]?.method === "POST"),
    ).toHaveLength(0);
    expect(
      await screen.findByRole("button", { name: "Open recovered task" }),
    ).toBeVisible();
  });
});

it("a lost reply recovered after newer navigation does not force Review", async () => {
  const delegate = serve();
  let finish!: (value: Response) => void;
  const fetch = vi.fn(
    async (input: RequestInfo | URL, options?: RequestInit) => {
      if (String(input).includes("/preparations/"))
        return new Promise<Response>((resolve) => (finish = resolve));
      return delegate(input, options);
    },
  );
  vi.stubGlobal("fetch", fetch);
  window.history.replaceState({}, "", "#literature");
  render(<App />);
  await selectAndPrepare();
  await waitFor(() =>
    expect(
      fetch.mock.calls.some((call) =>
        String(call[0]).includes("/preparations/"),
      ),
    ).toBe(true),
  );
  act(() => {
    window.history.replaceState({}, "", "#manuscript");
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  await act(async () => {
    finish(response({ ok: true, preparation: { state: "found", key }, task }));
  });
  expect(
    await screen.findByRole("button", { name: t("prepareOpenRecovered") }),
  ).toBeVisible();
  expect(window.location.hash).toBe("#manuscript");
});
it("legacy capability omission is explicitly keyless, without claiming durable reconciliation", async () => {
  const delegate = serve();
  const fetch = vi.fn(
    async (input: RequestInfo | URL, options?: RequestInit) => {
      if (String(input).endsWith("/workspace")) {
        const { prepare_reconciliation: _, ...capabilities } =
          workspace.capabilities;
        return response({ ...workspace, capabilities });
      }
      if (options?.method === "POST") return response({ ok: true, task });
      return delegate(input, options);
    },
  );
  vi.stubGlobal("fetch", fetch);
  window.history.replaceState({}, "", "#literature");
  render(<App />);
  await selectAndPrepare();
  expect(screen.getByText(t("prepareLegacyFallback"))).toBeInTheDocument();
  const write = fetch.mock.calls.find((call) => call[1]?.method === "POST")!;
  expect(JSON.parse(String(write[1]?.body))).not.toHaveProperty(
    "prepare_request",
  );
  expect(
    fetch.mock.calls.some((call) => String(call[0]).includes("/preparations/")),
  ).toBe(false);
  expect(window.localStorage.length).toBe(0);
});
it("storage-denied UI explains reload limits before offering an explicit session-only Prepare", async () => {
  const delegate = serve();
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new DOMException("Denied", "SecurityError");
  });
  const fetch = vi.fn(
    async (input: RequestInfo | URL, options?: RequestInit) =>
      options?.method === "POST"
        ? response({
            ok: true,
            preparation: { version: 1, key, disposition: "created" },
            task,
          })
        : delegate(input, options),
  );
  vi.stubGlobal("fetch", fetch);
  window.history.replaceState({}, "", "#literature");
  render(<App />);
  await selectAndPrepare();
  expect(screen.getByText(t("prepareStorageUnavailable"))).toBeVisible();
  expect(screen.getByText(t("prepareStorageConfirm"))).toBeVisible();
  expect(fetch.mock.calls.some((call) => call[1]?.method === "POST")).toBe(
    false,
  );
  await userEvent.click(
    screen.getByRole("button", { name: t("prepareSessionOnly") }),
  );
  await waitFor(() =>
    expect(
      fetch.mock.calls.filter((call) => call[1]?.method === "POST"),
    ).toHaveLength(1),
  );
  expect(
    fetch.mock.calls.some((call) => String(call[0]).endsWith("/run")),
  ).toBe(false);
});

it("independent exact lookup remains reviewable when subsequent project refresh fails", async () => {
  localStorage.setItem(
    storageKey,
    JSON.stringify({
      version: 1,
      workspace_instance_id: namespace,
      project_id: project.id,
      key,
      state: "pending",
    }),
  );
  let projectReads = 0;
  const fetch = vi.fn(
    async (input: RequestInfo | URL, options?: RequestInit) => {
      const url = String(input);
      if (options?.method === "POST") throw new Error("No write expected");
      if (url.endsWith("/workspace")) return response(workspace);
      if (url.includes("/preparations/"))
        return response({
          ok: true,
          preparation: { state: "found", key },
          task,
        });
      if (url.endsWith("/projects/river")) {
        projectReads++;
        return projectReads === 1
          ? response(detail)
          : response(
              { ok: false, error: "Synthetic project refresh unavailable" },
              503,
            );
      }
      throw new Error(`Unexpected request ${url}`);
    },
  );
  vi.stubGlobal("fetch", fetch);
  render(<App />);
  expect(await screen.findByText(t("refreshError"))).toBeVisible();
  await userEvent.click(
    screen.getByRole("button", { name: t("prepareOpenRecovered") }),
  );
  await waitFor(() => expect(window.location.hash).toBe("#review"));
  expect(
    fetch.mock.calls.filter((call) => call[1]?.method === "POST"),
  ).toHaveLength(0);
  expect(
    fetch.mock.calls.filter((call) =>
      String(call[0]).includes("/preparations/"),
    ),
  ).toHaveLength(1);
  expect(screen.getByText(t("refreshRetained"))).toBeVisible();
  expect(document.getElementById(`review-task-${task.id}`)).not.toBeNull();
  await waitFor(() =>
    expect(document.getElementById(`review-task-${task.id}`)).toHaveFocus(),
  );
}, 10000);

it("does not integrate an old namespace task when the authoritative workspace refresh changes namespace", async () => {
  localStorage.setItem(
    storageKey,
    JSON.stringify({
      version: 1,
      workspace_instance_id: namespace,
      project_id: project.id,
      key,
      state: "pending",
    }),
  );
  let workspaceReads = 0;
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/workspace")) {
      workspaceReads++;
      return response(
        workspaceReads === 1
          ? workspace
          : {
              ...workspace,
              capabilities: {
                ...workspace.capabilities,
                prepare_reconciliation: {
                  version: 1,
                  workspace_instance_id: "33333333-3333-4333-8333-333333333333",
                },
              },
            },
      );
    }
    if (url.includes("/preparations/"))
      return response({ ok: true, preparation: { state: "found", key }, task });
    return response(detail);
  });
  vi.stubGlobal("fetch", fetch);
  render(<App />);
  await waitFor(() => expect(workspaceReads).toBe(2));
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: t("prepareOpenRecovered") }),
    ).not.toBeInTheDocument(),
  );
  expect(document.getElementById(`review-task-${task.id}`)).toBeNull();
  expect(localStorage.getItem(storageKey)).not.toBeNull();
});

it("preserves an existing fresher task and unrelated tasks instead of overwriting them with the lookup snapshot", async () => {
  localStorage.setItem(
    storageKey,
    JSON.stringify({
      version: 1,
      workspace_instance_id: namespace,
      project_id: project.id,
      key,
      state: "pending",
    }),
  );
  const newer = {
    ...task,
    status: "awaiting_human",
    instructions: "Newer task state",
  };
  const other = { ...task, id: "unrelated-task" };
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/workspace")) return response(workspace);
    if (url.includes("/preparations/"))
      return response({ ok: true, preparation: { state: "found", key }, task });
    return response({ ...detail, tasks: [newer, other] });
  });
  vi.stubGlobal("fetch", fetch);
  window.history.replaceState({}, "", "#review");
  render(<App />);
  await screen.findByRole("button", { name: t("prepareOpenRecovered") });
  await waitFor(() =>
    expect(
      document.getElementById("review-task-unrelated-task"),
    ).toBeInTheDocument(),
  );
  const card = document.getElementById(`review-task-${task.id}`)!;
  expect(card).toHaveTextContent(t("awaiting_human"));
  expect(card).not.toHaveTextContent(t("ready"));
});

it("opens the exact recovered task while the bulk refresh is still pending", async () => {
  localStorage.setItem(
    storageKey,
    JSON.stringify({
      version: 1,
      workspace_instance_id: namespace,
      project_id: project.id,
      key,
      state: "pending",
    }),
  );
  let reads = 0;
  let finish!: (value: Response) => void;
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/workspace")) return response(workspace);
    if (url.includes("/preparations/"))
      return response({ ok: true, preparation: { state: "found", key }, task });
    reads++;
    if (reads === 1) return response(detail);
    return new Promise<Response>((resolve) => (finish = resolve));
  });
  vi.stubGlobal("fetch", fetch);
  render(<App />);
  await userEvent.click(
    await screen.findByRole("button", { name: t("prepareOpenRecovered") }),
  );
  expect(
    within(
      screen.getByRole("region", { name: t("prepareRecoveryTitle") }),
    ).getByRole("button", { name: t("dismiss") }),
  ).toBeDisabled();
  const targetWhilePending = document.getElementById(`review-task-${task.id}`);
  await act(async () => {
    finish(
      response({
        ...detail,
        tasks: [task],
        project: { ...project, goal: "Refreshed project goal" },
      }),
    );
  });
  expect(targetWhilePending).not.toBeNull();
  expect(await screen.findByText("Refreshed project goal")).toBeInTheDocument();
  expect(
    fetch.mock.calls.some((call) => String(call[0]).endsWith("/run")),
  ).toBe(false);
});
